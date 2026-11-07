import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.database.models import Alerta, Notificacao, Sincronizacao, Transferencia
from app.database.simulacao import SINCRONIZACOES, TRANSFERENCIAS
from app.rules.motor import avaliar
from app.rules.regras import REGRAS, Ocorrencia
from app.services import limites_pendencia

pytestmark = pytest.mark.integration

H = timedelta(hours=1)
ERROS = [t for t in TRANSFERENCIAS if t.status == "ERRO"]
ATRASADAS = [t for t in TRANSFERENCIAS if t.status == "PENDENTE" and t.criada_ha > 24 * H]
CRITICAS = [t for t in ATRASADAS if t.criada_ha > 48 * H]
COI_ERRADO = [t for t in TRANSFERENCIAS if t.problemas_coi]


def _ultima_sync_com_erro() -> int:
    ultimas: dict[str, tuple] = {}
    for empresa, ha, status, *_ in SINCRONIZACOES:
        if empresa not in ultimas or ha < ultimas[empresa][0]:
            ultimas[empresa] = (ha, status)
    return sum(1 for _, status in ultimas.values() if status == "erro")


def _agora(db) -> datetime:

    return db.scalar(select(func.now()))


def _abertos(db, regra: str | None = None) -> list[Alerta]:
    stmt = select(Alerta).where(Alerta.status == "ABERTO")
    if regra:
        stmt = stmt.where(Alerta.regra == regra)
    return list(db.scalars(stmt))


def test_seed_tem_cada_situacao_coberta_pelas_regras():
    assert ERROS and ATRASADAS and CRITICAS and COI_ERRADO and _ultima_sync_com_erro()


def test_primeira_avaliacao_abre_um_alerta_por_situacao(api_db):
    resultado = avaliar(api_db, _agora(api_db))

    assert len(_abertos(api_db, "transferencia_erro")) == len(ERROS)
    assert len(_abertos(api_db, "transferencia_atrasada")) == len(ATRASADAS)
    assert len(_abertos(api_db, "sincronizacao_erro")) == _ultima_sync_com_erro()
    assert len(_abertos(api_db, "transferencia_coi_errado")) == len(COI_ERRADO)
    assert resultado.abertos == (
        len(ERROS) + len(ATRASADAS) + _ultima_sync_com_erro() + len(COI_ERRADO)
    )

    criticos = [a for a in _abertos(api_db, "transferencia_atrasada") if a.severidade == "CRITICAL"]
    assert len(criticos) == len(CRITICAS)


def test_toda_abertura_warning_ou_acima_gera_uma_notificacao(api_db):
    avaliar(api_db, _agora(api_db))
    alertas = _abertos(api_db)
    assert all(a.severidade != "INFO" for a in alertas)
    for alerta in alertas:
        assert [(n.tipo, n.status, n.canal) for n in alerta.notificacoes] == [
            ("ABERTURA", "PENDENTE", "telegram")
        ]


def test_avaliar_de_novo_nao_duplica_alerta_nem_notificacao(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alertas = api_db.scalar(select(func.count()).select_from(Alerta))
    notificacoes = api_db.scalar(select(func.count()).select_from(Notificacao))

    resultado = avaliar(api_db, agora + timedelta(minutes=1))

    assert resultado.abertos == resultado.escalados == resultado.resolvidos == 0
    assert resultado.mantidos == alertas
    assert api_db.scalar(select(func.count()).select_from(Alerta)) == alertas
    assert api_db.scalar(select(func.count()).select_from(Notificacao)) == notificacoes
    assert all(a.visto_em == agora + timedelta(minutes=1) for a in _abertos(api_db))


def test_situacao_que_some_resolve_o_alerta_e_avisa(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alerta = _abertos(api_db, "transferencia_erro")[0]
    api_db.execute(
        update(Transferencia)
        .where(Transferencia.id == alerta.transferencia_id)
        .values(status="PROCESSADA")
    )

    resultado = avaliar(api_db, agora + timedelta(minutes=5))

    assert resultado.resolvidos == 1
    assert alerta.status == "RESOLVIDO"
    assert alerta.resolvido_em == agora + timedelta(minutes=5)
    assert [n.tipo for n in alerta.notificacoes] == ["ABERTURA", "RESOLUCAO"]


def test_situacao_que_volta_abre_alerta_novo(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alerta = _abertos(api_db, "transferencia_erro")[0]
    transferencia_id = alerta.transferencia_id
    api_db.execute(
        update(Transferencia).where(Transferencia.id == transferencia_id).values(status="OK")
    )
    avaliar(api_db, agora + timedelta(minutes=1))
    api_db.execute(
        update(Transferencia).where(Transferencia.id == transferencia_id).values(status="ERRO")
    )

    avaliar(api_db, agora + timedelta(minutes=2))

    historico = api_db.scalars(
        select(Alerta).where(Alerta.chave == alerta.chave).order_by(Alerta.id)
    ).all()
    assert [a.status for a in historico] == ["RESOLVIDO", "ABERTO"]


def test_pendencia_que_envelhece_escala_para_critico(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alerta = next(
        a for a in _abertos(api_db, "transferencia_atrasada") if a.severidade == "WARNING"
    )
    criada = api_db.get(Transferencia, alerta.transferencia_id).data_criacao

    resultado = avaliar(api_db, criada + 49 * H)

    assert resultado.escalados >= 1
    assert alerta.severidade == "CRITICAL"
    assert [n.tipo for n in alerta.notificacoes] == ["ABERTURA", "ESCALADA"]


def test_sincronizacao_nova_com_sucesso_resolve_o_alerta(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alerta = _abertos(api_db, "sincronizacao_erro")[0]
    api_db.add(
        Sincronizacao(
            empresa_id=alerta.empresa_id, tipo="transferencias", inicio=agora, status="sucesso"
        )
    )
    api_db.flush()

    avaliar(api_db, agora + timedelta(minutes=1))

    assert alerta.status == "RESOLVIDO"


def test_severidade_info_abre_alerta_sem_notificar(api_db):
    agora = datetime.now(UTC)

    def regra_info(db, _agora):
        return [Ocorrencia("teste_info", "teste_info:1", "INFO", "so registro", "-")]

    avaliar(api_db, agora, regras={"teste_info": regra_info})
    alerta = _abertos(api_db, "teste_info")[0]
    assert alerta.notificacoes == []

    avaliar(api_db, agora, regras={"teste_info": lambda db, a: []})
    assert alerta.status == "RESOLVIDO"
    assert alerta.notificacoes == []


def test_avaliar_um_subconjunto_nao_resolve_alertas_de_outras_regras(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    total = len(_abertos(api_db))

    avaliar(api_db, agora, regras={"transferencia_erro": REGRAS["transferencia_erro"]})

    assert len(_abertos(api_db)) == total


def test_mensagem_de_sincronizacao_traz_hora_no_fuso_de_exibicao(api_db):
    avaliar(api_db, _agora(api_db))
    alerta = _abertos(api_db, "sincronizacao_erro")[0]
    linha = next(li for li in alerta.mensagem.splitlines() if li.startswith("Início: "))
    assert re.fullmatch(r"Início: \d{2}/\d{2} \d{2}:\d{2}", linha)


def test_coi_errado_abre_alerta_critico_com_o_problema_e_notifica(api_db):
    avaliar(api_db, _agora(api_db))
    alertas = _abertos(api_db, "transferencia_coi_errado")

    assert sorted(a.detalhes["id_erp"] for a in alertas) == sorted(
        f"DEMO-TRF-{t.numero:04d}" for t in COI_ERRADO
    )
    for alerta in alertas:
        assert alerta.severidade == "CRITICAL"
        assert "COI ERRADO" in alerta.titulo
        assert alerta.detalhes["problemas"]
        assert alerta.detalhes["problemas"][0] in alerta.mensagem
        assert [n.tipo for n in alerta.notificacoes] == ["ABERTURA"]


def test_coi_corrigido_resolve_o_alerta(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alerta = _abertos(api_db, "transferencia_coi_errado")[0]
    api_db.execute(
        update(Transferencia)
        .where(Transferencia.id == alerta.transferencia_id)
        .values(problemas_coi=[])
    )

    avaliar(api_db, agora + timedelta(minutes=1))

    assert alerta.status == "RESOLVIDO"
    assert [n.tipo for n in alerta.notificacoes] == ["ABERTURA", "RESOLUCAO"]


def test_nota_cancelada_com_coi_errado_nao_e_alerta(api_db):
    agora = _agora(api_db)
    avaliar(api_db, agora)
    alerta = _abertos(api_db, "transferencia_coi_errado")[0]
    api_db.execute(
        update(Transferencia)
        .where(Transferencia.id == alerta.transferencia_id)
        .values(status="CANCELADA")
    )

    avaliar(api_db, agora + timedelta(minutes=1))

    assert alerta.status == "RESOLVIDO"


def test_pendente_sem_entrada_avisa_com_24h_e_e_critica_com_48h(api_db):
    agora = _agora(api_db)
    alvo = api_db.scalar(select(Transferencia).where(Transferencia.status == "PENDENTE"))
    chave = f"transferencia_atrasada:{alvo.id}"

    for idade, esperado in ((23 * H, None), (25 * H, "WARNING"), (49 * H, "CRITICAL")):
        alvo.data_criacao = agora - idade
        api_db.flush()
        avaliar(api_db, agora)
        severidades = {a.chave: a.severidade for a in _abertos(api_db, "transferencia_atrasada")}
        assert severidades.get(chave) == esperado, idade


def test_limites_mudados_na_tela_valem_para_o_alerta(api_db):
    agora = _agora(api_db)
    limites_pendencia.definir(api_db, 6, 12, usuario_id=None, usuario_nome="Adm", agora=agora)
    alvo = api_db.scalar(select(Transferencia).where(Transferencia.status == "PENDENTE"))
    chave = f"transferencia_atrasada:{alvo.id}"

    for idade, esperado in ((5 * H, None), (7 * H, "WARNING"), (13 * H, "CRITICAL")):
        alvo.data_criacao = agora - idade
        api_db.flush()
        avaliar(api_db, agora)
        severidades = {a.chave: a.severidade for a in _abertos(api_db, "transferencia_atrasada")}
        assert severidades.get(chave) == esperado, idade
