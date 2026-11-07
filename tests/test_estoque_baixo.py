from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.database.models import (
    AlertaConfiguracao,
    AlertaDestino,
    Atividade,
    EstoqueBaixoAvisado,
    EstoqueEmpresaLocalLote,
    ExcecaoCobertura,
    Notificacao,
    ParametrosEstoqueBaixo,
)
from app.services import estoque_baixo as service
from app.services.estoque import JanelaVendas
from tests.conftest import app_com_sessao, token_para

TZ = ZoneInfo("America/Porto_Velho")


def _p(horarios, ultima=None) -> ParametrosEstoqueBaixo:
    return ParametrosEstoqueBaixo(
        id=1, ativo=True, dias_cobertura=7, horarios=horarios, ultima_execucao=ultima
    )


def test_horario_vencido_roda_uma_vez_e_respeita_o_atraso():
    oito = datetime(2026, 11, 3, 8, 0, tzinfo=TZ)
    p = _p(["08:00", "14:00"])

    assert service._horario_vencido(p, oito - timedelta(minutes=1), TZ) is None
    assert service._horario_vencido(p, oito + timedelta(minutes=2), TZ) == oito
    p.ultima_execucao = oito + timedelta(minutes=2)
    assert service._horario_vencido(p, oito + timedelta(minutes=30), TZ) is None

    assert service._horario_vencido(_p(["08:00"]), oito + timedelta(hours=4), TZ) is None


def test_quantidade_em_texto():
    assert service._quantidade(Decimal("2.500")) == "2,5"
    assert service._quantidade(Decimal("0.1234")) == "0,12"
    assert service._quantidade(Decimal("10")) == "10"


integration = pytest.mark.integration


@pytest.fixture
def eb_db(api_db, criar_usuario_teste):
    api_db.execute(delete(AlertaConfiguracao))
    api_db.execute(delete(AlertaDestino))
    api_db.execute(delete(Atividade))
    api_db.add(AlertaDestino(nome="Padrão", chat_id=None))
    api_db.flush()
    api_db.info["admin"] = criar_usuario_teste("admin.eb", "ADMIN", modulos=["ADMINISTRACAO"])
    _saldos(api_db)
    return api_db


SALDOS = {"DEMO-PROD-001": 0, "DEMO-PROD-002": 20, "DEMO-PROD-003": 10**6}


def _saldos(db) -> None:
    janela = JanelaVendas.ultimos(30, _hoje())
    agora = datetime.now(UTC)
    for loja in service.lojas_que_vendem(db, janela):
        for produto, saldo in SALDOS.items():
            db.add(
                EstoqueEmpresaLocalLote(
                    empresa_id=loja.id,
                    id_produto=produto,
                    id_subproduto=produto,
                    id_local_estoque="1",
                    saldo_atual=Decimal(saldo),
                    saldo_reservado=Decimal(0),
                    saldo_disponivel=Decimal(saldo),
                    sincronizado_em=agora,
                )
            )
    db.flush()


def _hoje():
    return datetime.now(TZ).date()


def _configurar(db, dias=30, horarios=("08:00",), por_loja=None):
    return service.salvar_parametros(
        db,
        ativo=True,
        dias_cobertura=dias,
        dias_por_empresa=por_loja or {},
        janela_dias=30,
        horarios=list(horarios),
        usuario=db.info["admin"],
    )


@integration
def test_excecao_da_loja_fica_fora_do_estoque_baixo(eb_db):
    janela = JanelaVendas.ultimos(30, _hoje())
    [loja, outra, *_] = service.lojas_que_vendem(eb_db, janela)
    eb_db.add(
        ExcecaoCobertura(
            empresa_id=loja.id,
            id_produto="DEMO-PROD-001",
            id_subproduto="DEMO-PROD-001",
            usuario_nome="Teste",
            criado_em=datetime.now(UTC),
        )
    )
    eb_db.flush()

    assert [b.id_produto for b in service.produtos_baixos(eb_db, loja, 30, janela)] == [
        "DEMO-PROD-002"
    ]

    assert "DEMO-PROD-001" in [
        b.id_produto for b in service.produtos_baixos(eb_db, outra, 30, janela)
    ]


@integration
def test_minimo_e_a_media_vezes_os_dias(eb_db):
    janela = JanelaVendas.ultimos(30, _hoje())
    [loja, *_] = service.lojas_que_vendem(eb_db, janela)

    muitos = service.produtos_baixos(eb_db, loja, 30, janela)
    poucos = service.produtos_baixos(eb_db, loja, 1, janela)

    assert [b.id_produto for b in muitos] == ["DEMO-PROD-001", "DEMO-PROD-002"]
    assert [b.id_produto for b in poucos] == ["DEMO-PROD-001"]
    for b in muitos:
        assert b.media > 0 and b.disponivel < b.minimo
        assert b.minimo == pytest.approx(b.media * 30)

    dias = [b.disponivel / b.media for b in muitos]
    assert dias == sorted(dias)


@integration
def test_dias_da_loja_vencem_o_geral(eb_db):
    janela = JanelaVendas.ultimos(30, _hoje())
    [loja, *_] = service.lojas_que_vendem(eb_db, janela)
    p = _configurar(eb_db, dias=1, por_loja={loja.id: 365})
    assert service.dias_da_loja(p, loja.id) == 365
    [situacao] = [s for s in service.situacao(eb_db, _hoje()) if s.empresa.id == loja.id]
    assert situacao.dias == 365 and situacao.baixos


@integration
def test_parametros_invalidos(eb_db):
    with pytest.raises(service.ParametrosInvalidos, match="HH:MM"):
        _configurar(eb_db, horarios=["8h"])
    with pytest.raises(service.ParametrosInvalidos, match="Loja"):
        _configurar(eb_db, por_loja={999999: 5})


@integration
def test_resumo_traz_so_os_novos_e_reavisa_quem_baixa_de_novo(eb_db):
    _configurar(eb_db, dias=365, horarios=["08:00", "14:00"])
    hoje = _hoje()
    oito = datetime(hoje.year, hoje.month, hoje.day, 8, 1, tzinfo=TZ)

    lojas = service.processar(eb_db, oito, TZ)
    assert lojas and lojas >= 1
    assert service.processar(eb_db, oito + timedelta(minutes=5), TZ) is None
    avisos = eb_db.scalars(select(Atividade).where(Atividade.tipo == "estoque_baixo")).all()
    assert len(avisos) == lojas
    primeiro = avisos[0]
    assert "com estoque baixo" in primeiro.resumo
    assert primeiro.valores["produtos"].startswith("• ")

    assert (
        eb_db.scalar(
            select(func.count())
            .select_from(Notificacao)
            .where(Notificacao.atividade_id == primeiro.id)
        )
        == 1
    )

    loja_id = primeiro.empresas[0]
    alvo = eb_db.scalars(
        select(EstoqueBaixoAvisado).where(EstoqueBaixoAvisado.empresa_id == loja_id)
    ).first()
    filtro_saldo = (
        (EstoqueEmpresaLocalLote.empresa_id == loja_id)
        & (EstoqueEmpresaLocalLote.id_produto == alvo.id_produto)
        & (EstoqueEmpresaLocalLote.id_subproduto == alvo.id_subproduto)
    )
    eb_db.execute(
        update(EstoqueEmpresaLocalLote).where(filtro_saldo).values(saldo_disponivel=10**9)
    )
    duas = datetime(hoje.year, hoje.month, hoje.day, 14, 1, tzinfo=TZ)
    assert service.processar(eb_db, duas, TZ) == 0
    chave = (alvo.empresa_id, alvo.id_produto, alvo.id_subproduto)
    assert eb_db.get(EstoqueBaixoAvisado, chave) is None

    eb_db.execute(update(EstoqueEmpresaLocalLote).where(filtro_saldo).values(saldo_disponivel=0))
    amanha = duas + timedelta(days=1) - timedelta(hours=6)
    assert service.processar(eb_db, amanha, TZ) == 1
    ultimo = eb_db.scalars(
        select(Atividade).where(Atividade.tipo == "estoque_baixo").order_by(Atividade.id.desc())
    ).first()
    assert ultimo.valores["quantidade"] == "1" and alvo.id_subproduto in ultimo.valores["produtos"]


@integration
def test_sem_configuracao_ou_desligado_nao_avisa(eb_db):
    agora = datetime.now(UTC)
    assert service.processar(eb_db, agora, TZ) is None
    p = _configurar(eb_db)
    p.ativo = False
    assert service.processar(eb_db, agora, TZ) is None


@integration
def test_api_configura_e_mostra_a_situacao(eb_db, criar_usuario_teste):
    app = app_com_sessao(eb_db)
    api = TestClient(app, headers=token_para(app, eb_db.info["admin"]))
    url = "/api/v1/admin/estoque-baixo"

    padrao = api.get(url).json()
    assert padrao["configurado"] is False and padrao["horarios"] == ["08:00"]

    invalido = api.put(url, json={"dias_cobertura": 7, "horarios": ["25:00"]})
    assert invalido.status_code == 422 and "HH:MM" in invalido.json()["detail"]
    salvo = api.put(url, json={"dias_cobertura": 365, "horarios": ["14:00", "08:00"]}).json()
    assert salvo["configurado"] and salvo["horarios"] == ["08:00", "14:00"]
    assert salvo["atualizado_por"] == "Admin.Eb"

    situacao = api.get(f"{url}/situacao", params={"limite": 3}).json()
    assert situacao["lojas"] and all(len(s["produtos"]) <= 3 for s in situacao["lojas"])
    assert any(s["total"] > 0 for s in situacao["lojas"])

    [registro] = eb_db.scalars(select(Atividade).where(Atividade.tipo == "alertas_alterados")).all()
    assert "ligou o aviso de estoque baixo" in registro.resumo

    operador = criar_usuario_teste("op.eb", "OPERADOR", modulos=["ALERTAS"])
    assert TestClient(app, headers=token_para(app, operador)).get(url).status_code == 403
    app.dependency_overrides.clear()
