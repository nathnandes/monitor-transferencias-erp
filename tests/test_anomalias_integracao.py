import os
import subprocess
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.database.models import (
    Alerta,
    AlertaConfiguracao,
    AnomaliaExecucao,
    AnomaliaTransferencia,
    Empresa,
    Transferencia,
    TransferenciaItem,
    TransferenciaTratativa,
)
from app.rules.catalogo import CATALOGO
from app.rules.motor import avaliar
from app.rules.regras import DIAS_ALERTA_ANOMALIA, REGRAS, transferencia_anomala
from app.scripts import demo_anomalias
from app.services import anomalias as service
from app.services.controle_transferencias import Filtros
from app.workers.anomalias import executar_ciclo, rodar_detector
from tests.conftest import app_com_sessao, token_para
from tests.sync_fakes import fabrica_de

pytestmark = pytest.mark.integration

TZ = ZoneInfo("America/Porto_Velho")
AGORA = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def empresas(db_vazio):
    lista = [
        Empresa(id_erp=f"T-{c}", codigo=c, nome=f"Empresa Teste {c}", ambiente="test", ativo=True)
        for c in ("01", "02", "03")
    ]
    db_vazio.add_all(lista)
    db_vazio.flush()
    return lista


def _nota(
    empresas,
    numero: int,
    emitida: datetime,
    *,
    valor: str = "1000.00",
    horas_transito: float | None = 10.0,
    enviada: str = "100",
    recebida: str | None = None,
    **campos,
) -> Transferencia:
    recebeu = horas_transito is not None
    t = Transferencia(
        id_erp=f"N{numero}",
        empresa_origem_id=empresas[0].id,
        empresa_destino_id=empresas[1].id,
        status="PROCESSADA" if recebeu else "PENDENTE",
        data_criacao=emitida,
        data_processamento=emitida + timedelta(hours=horas_transito) if recebeu else None,
        quantidade_itens=5,
        numero_nota=str(numero),
        valor_total=Decimal(valor),
        raw_data={},
    )
    for chave, novo in campos.items():
        setattr(t, chave, novo)
    t.itens = [
        TransferenciaItem(
            id_produto_erp="P1",
            quantidade_solicitada=Decimal(enviada),
            quantidade_processada=Decimal(recebida or enviada) if recebeu else None,
            raw_data={},
        )
    ]
    return t


def _historico(db, empresas, quantidade: int = 80) -> None:
    db.add_all(
        _nota(
            empresas,
            n,
            AGORA - timedelta(days=10 + n % 60, hours=n % 5),
            valor=f"{1000 + (n * 37) % 300}.00",
            horas_transito=8 + n % 5,
            recebida=str(100 - n // 8) if n % 8 == 0 else None,
        )
        for n in range(1, quantidade + 1)
    )
    db.flush()


@pytest.fixture
def settings():
    return get_settings().model_copy(
        update={
            "anomalias_minimo_treino": 50,
            "anomalias_janela_avaliacao_dias": 7,
            "anomalias_historico_dias": 365,
            "tz": "America/Porto_Velho",
        }
    )


def _estranha(empresas, numero: int = 9001, **campos) -> Transferencia:
    padrao = {
        "valor": "90000.00",
        "horas_transito": 300.0,
        "recebida": "40",
        "emitida": AGORA - timedelta(days=2, hours=9),
    }
    padrao.update(campos)
    return _nota(empresas, numero, padrao.pop("emitida"), **padrao)


def _ligar_regra(db) -> None:
    db.add(AlertaConfiguracao(regra="transferencia_anomala", ativo=True, campos=[]))
    db.flush()


def test_conversao_usa_hora_local_e_soma_os_itens(db_vazio, empresas):
    emitida = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    t = _nota(empresas, 1, emitida, enviada="10", recebida="8")
    t.itens.append(
        TransferenciaItem(
            id_produto_erp="P2",
            quantidade_solicitada=Decimal("5"),
            quantidade_processada=None,
            raw_data={},
        )
    )
    db_vazio.add(t)
    db_vazio.flush()

    [r] = service.carregar_treino(
        db_vazio, inicio=emitida - timedelta(days=1), fim=emitida + timedelta(days=1), tz=TZ
    )
    assert r.id == str(t.id)
    assert r.emitida_em.hour == 10
    assert r.valor == 1000.0
    assert r.quantidade_enviada == 15
    assert r.quantidade_recebida == 8
    assert r.origem == "01 - Empresa Teste 01"


def test_pendente_nao_tem_quantidade_recebida(db_vazio, empresas):
    emitida = AGORA - timedelta(days=1)
    db_vazio.add(_nota(empresas, 1, emitida, horas_transito=None))
    db_vazio.flush()
    [r] = service.carregar_para_avaliar(db_vazio, inicio=emitida - timedelta(days=1), tz=TZ)
    assert r.pendente
    assert r.quantidade_recebida is None


@pytest.mark.parametrize(
    "campos",
    [
        {"status": "CANCELADA"},
        {"entre_empresas": False},
        {"valor_total": None},
        {"empresa_destino_id": None},
    ],
)
def test_ficam_de_fora_as_notas_que_nao_da_para_julgar(db_vazio, empresas, campos):
    emitida = AGORA - timedelta(days=1)
    db_vazio.add(_nota(empresas, 1, emitida, **campos))
    db_vazio.flush()
    assert service.carregar_para_avaliar(db_vazio, inicio=emitida - timedelta(days=1), tz=TZ) == []


def test_sem_historico_suficiente_nao_avalia_nada(db_vazio, empresas, settings):
    _historico(db_vazio, empresas, quantidade=10)
    db_vazio.add(_estranha(empresas))
    db_vazio.flush()

    execucao = rodar_detector(db_vazio, settings, AGORA)

    assert execucao.status == "sem_historico"
    assert execucao.notas_treino == 10
    assert "mínimo" in execucao.mensagem
    assert db_vazio.scalars(select(AnomaliaTransferencia)).all() == []


def test_treino_nao_inclui_a_janela_de_avaliacao(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    novas = [_nota(empresas, 5000 + i, AGORA - timedelta(days=1 + i)) for i in range(3)]
    db_vazio.add_all(novas)
    db_vazio.flush()

    execucao = rodar_detector(db_vazio, settings, AGORA)

    assert execucao.status == "sucesso"
    assert execucao.notas_treino == 80
    assert execucao.notas_avaliadas == 3


def test_nota_estranha_e_sinalizada_com_motivo_e_nota_comum_nao(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    estranha = _estranha(empresas)
    comum = _nota(empresas, 9002, AGORA - timedelta(days=2, hours=3), valor="1100.00")
    db_vazio.add_all([estranha, comum])
    db_vazio.flush()

    rodar_detector(db_vazio, settings, AGORA)

    a = db_vazio.get(AnomaliaTransferencia, estranha.id)
    b = db_vazio.get(AnomaliaTransferencia, comum.id)
    assert a.sinalizada and a.score > a.limiar and a.motivos
    assert a.motivos[0]["texto"]
    assert a.com_entrada
    assert not b.sinalizada and b.motivos == []
    assert a.score > b.score


def test_score_fica_estavel_entre_rodadas(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    t = _estranha(empresas)
    db_vazio.add(t)
    db_vazio.flush()

    rodar_detector(db_vazio, settings, AGORA)
    antes = db_vazio.get(AnomaliaTransferencia, t.id)
    primeira_execucao = antes.execucao_id
    segunda = rodar_detector(db_vazio, settings, AGORA + timedelta(hours=1))

    assert segunda.notas_avaliadas == 0
    db_vazio.refresh(antes)
    assert antes.execucao_id == primeira_execucao


def test_nota_e_reavaliada_quando_a_entrada_chega(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    t = _nota(
        empresas, 9001, AGORA - timedelta(days=3, hours=4), valor="1150.00", horas_transito=None
    )
    db_vazio.add(t)
    db_vazio.flush()

    rodar_detector(db_vazio, settings, AGORA)
    linha = db_vazio.get(AnomaliaTransferencia, t.id)
    assert not linha.com_entrada
    assert not linha.sinalizada

    t.status = "PROCESSADA"
    t.data_processamento = t.data_criacao + timedelta(hours=10)
    t.itens[0].quantidade_processada = Decimal("20")
    db_vazio.flush()

    segunda = rodar_detector(db_vazio, settings, AGORA + timedelta(hours=1))
    assert segunda.notas_avaliadas == 1
    db_vazio.refresh(linha)
    assert linha.com_entrada
    assert linha.sinalizada
    assert any("faltaram" in m["texto"] for m in linha.motivos)


def test_ciclo_so_roda_quando_venceu(db_vazio, empresas, settings):
    _historico(db_vazio, empresas, quantidade=10)
    fabrica = fabrica_de(db_vazio)
    assert executar_ciclo(fabrica, settings, agora=lambda: AGORA).status == "sem_historico"
    meio = AGORA + timedelta(seconds=settings.anomalias_intervalo_segundos - 1)
    assert executar_ciclo(fabrica, settings, agora=lambda: meio) is None
    assert executar_ciclo(fabrica, settings, forcar=True, agora=lambda: meio) is not None
    depois = meio + timedelta(seconds=settings.anomalias_intervalo_segundos)
    assert executar_ciclo(fabrica, settings, agora=lambda: depois) is not None


def test_erro_na_rodada_fica_registrado_sem_derrubar_o_worker(
    db_vazio, empresas, settings, monkeypatch
):
    def falhar(*_args, **_kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr("app.workers.anomalias.rodar_detector", falhar)
    execucao = executar_ciclo(fabrica_de(db_vazio), settings, agora=lambda: AGORA)
    assert execucao.status == "erro"
    assert "falha simulada" in execucao.mensagem


def test_regra_nasce_desligada_e_esta_no_catalogo():
    definicao = CATALOGO["transferencia_anomala"]
    assert definicao.ativo_padrao is False
    assert "transferencia_anomala" in REGRAS
    assert definicao.campo("emitida_por") is None


def test_desligada_nao_abre_alerta(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    db_vazio.add(_estranha(empresas))
    db_vazio.flush()
    rodar_detector(db_vazio, settings, AGORA)

    avaliar(db_vazio, AGORA)

    alertas = db_vazio.scalars(select(Alerta).where(Alerta.regra == "transferencia_anomala"))
    assert alertas.all() == []


def test_ligada_abre_um_alerta_e_resolve_com_a_tratativa(db_vazio, empresas, settings):
    _ligar_regra(db_vazio)
    _historico(db_vazio, empresas)
    t = _estranha(empresas)
    db_vazio.add(t)
    db_vazio.flush()
    rodar_detector(db_vazio, settings, AGORA)

    avaliar(db_vazio, AGORA)
    [alerta] = db_vazio.scalars(select(Alerta).where(Alerta.regra == "transferencia_anomala")).all()
    assert alerta.status == "ABERTO"
    assert alerta.severidade == "WARNING"
    assert alerta.transferencia_id == t.id
    assert "fora do padrão" in alerta.titulo
    assert alerta.detalhes["campos"]["motivos"].startswith("• ")

    rodar_detector(db_vazio, settings, AGORA + timedelta(hours=1))
    avaliar(db_vazio, AGORA + timedelta(hours=1))
    assert db_vazio.get(Alerta, alerta.id).status == "ABERTO"

    db_vazio.add(
        TransferenciaTratativa(
            transferencia_id=t.id, usuario_nome="Ana", situacao="RESOLVIDA", observacao="Conferida"
        )
    )
    db_vazio.flush()
    avaliar(db_vazio, AGORA + timedelta(hours=2))
    assert db_vazio.get(Alerta, alerta.id).status == "RESOLVIDO"


def test_tratativa_em_analise_mantem_o_alerta(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    t = _estranha(empresas)
    db_vazio.add(t)
    db_vazio.flush()
    rodar_detector(db_vazio, settings, AGORA)
    db_vazio.add(
        TransferenciaTratativa(
            transferencia_id=t.id, usuario_nome="Ana", situacao="EM_ANALISE", observacao="Olhando"
        )
    )
    db_vazio.flush()
    assert [o.transferencia_id for o in transferencia_anomala(db_vazio, AGORA)] == [t.id]


def test_regra_ignora_cancelada_e_sinalizada_antiga(db_vazio, empresas, settings):
    _historico(db_vazio, empresas)
    t = _estranha(empresas)
    db_vazio.add(t)
    db_vazio.flush()
    rodar_detector(db_vazio, settings, AGORA)
    assert transferencia_anomala(db_vazio, AGORA)

    futuro = AGORA + timedelta(days=DIAS_ALERTA_ANOMALIA + 1)
    assert transferencia_anomala(db_vazio, futuro) == []

    t.status = "CANCELADA"
    db_vazio.flush()
    assert transferencia_anomala(db_vazio, AGORA) == []


def _preparar_painel(db, empresas, settings) -> Transferencia:
    _historico(db, empresas)
    t = _estranha(empresas)
    db.add_all([t, _nota(empresas, 9002, AGORA - timedelta(days=2, hours=3), valor="1100.00")])
    db.flush()
    rodar_detector(db, settings, AGORA)
    return t


def test_painel_filtra_por_periodo_e_empresa(db_vazio, empresas, settings):
    t = _preparar_painel(db_vazio, empresas, settings)

    tudo = service.painel(db_vazio, Filtros(), TZ)
    assert tudo.analisadas == 2
    assert tudo.sinalizadas == 1
    assert [a.transferencia_id for a in tudo.lista] == [t.id]
    assert tudo.execucao.status == "sucesso"

    data = t.data_criacao.astimezone(TZ).date()
    assert service.painel(db_vazio, Filtros(data_inicial=data), TZ).sinalizadas == 1
    depois = data + timedelta(days=1)
    assert service.painel(db_vazio, Filtros(data_inicial=depois), TZ).sinalizadas == 0
    assert service.painel(db_vazio, Filtros(empresa="02"), TZ).sinalizadas == 1
    assert service.painel(db_vazio, Filtros(empresa="03"), TZ).sinalizadas == 0


def test_painel_sem_nenhuma_rodada(db_vazio):
    dados = service.painel(db_vazio, Filtros(), TZ)
    assert dados.execucao is None
    assert (dados.analisadas, dados.sinalizadas, dados.lista) == (0, 0, [])


def test_painel_mostra_a_ultima_tratativa(db_vazio, empresas, settings):
    t = _preparar_painel(db_vazio, empresas, settings)
    db_vazio.add(
        TransferenciaTratativa(
            transferencia_id=t.id, usuario_nome="Ana", situacao="EM_ANALISE", observacao="Olhando"
        )
    )
    db_vazio.flush()
    assert service.painel(db_vazio, Filtros(), TZ).tratativas[t.id].situacao == "EM_ANALISE"


@pytest.fixture
def cliente(db_vazio, criar_usuario_teste):
    app = app_com_sessao(db_vazio)

    def _cliente(modulos: list[str]) -> TestClient:
        usuario = criar_usuario_teste("conferente", "OPERADOR", modulos=modulos)
        return TestClient(app, headers=token_para(app, usuario))

    yield _cliente
    app.dependency_overrides.clear()


def test_api_entrega_o_painel(cliente, db_vazio, empresas, settings):
    t = _preparar_painel(db_vazio, empresas, settings)
    resposta = cliente(["TRANSFERENCIAS"]).get("/api/v1/transferencias/anomalias")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["sinalizadas"] == 1
    [item] = corpo["lista"]
    assert item["transferencia"]["id"] == t.id
    assert item["transferencia"]["origem"]["codigo"] == "01"
    assert item["motivos"]
    assert item["score"] > item["limiar"]
    assert corpo["execucao"]["status"] == "sucesso"


def test_api_exige_o_modulo(cliente):
    resposta = cliente(["DASHBOARD"]).get("/api/v1/transferencias/anomalias")
    assert resposta.status_code == 403


def test_api_recusa_intervalo_invertido(cliente):
    resposta = cliente(["TRANSFERENCIAS"]).get(
        "/api/v1/transferencias/anomalias",
        params={"data_inicial": "2026-06-10", "data_final": "2026-06-01"},
    )
    assert resposta.status_code == 422


def test_seed_da_demo_alimenta_o_detector_e_nao_acumula(db_vazio, settings):
    agora = datetime.now(TZ)
    quantidade = demo_anomalias.aplicar(db_vazio, settings, agora)
    assert quantidade == demo_anomalias.aplicar(db_vazio, settings, agora)

    notas = db_vazio.scalars(
        select(Transferencia).where(Transferencia.id_erp.startswith(demo_anomalias.PREFIXO_DEMO))
    ).all()
    assert len(notas) == quantidade
    assert all(t.raw_data["simulado"] is True for t in notas)
    assert all(t.entre_empresas and t.problemas_coi == [] for t in notas)

    janela = settings.model_copy(update={"anomalias_janela_avaliacao_dias": 30})
    execucao = rodar_detector(db_vazio, janela, agora.astimezone(UTC))
    assert execucao.status == "sucesso"
    assert execucao.notas_sinalizadas > 0
    assert db_vazio.scalars(select(AnomaliaExecucao)).first() is not None


def test_seed_da_demo_recusa_producao(monkeypatch, capsys):
    monkeypatch.setattr(
        demo_anomalias,
        "get_settings",
        lambda: get_settings().model_copy(update={"app_env": "production", "environment": ""}),
    )
    assert demo_anomalias.main(["seed"]) == 2
    assert "RECUSADO" in capsys.readouterr().err


def test_api_e_monitor_nao_carregam_scikit_learn():
    codigo = textwrap.dedent(
        """
        import sys
        import app.main
        import app.workers.monitor
        assert "sklearn" not in sys.modules
        """
    )
    subprocess.run(
        [sys.executable, "-c", codigo],
        check=True,
        env={**os.environ, "PYTHONPATH": "src"},
        timeout=120,
    )
