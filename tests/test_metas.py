from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.database.models import (
    AlertaConfiguracao,
    AlertaDestino,
    Atividade,
    Empresa,
    MetaVenda,
    Notificacao,
    Venda,
    Vendedor,
)
from app.services import metas
from tests.conftest import app_com_sessao, token_para

TZ = ZoneInfo("America/Porto_Velho")


@pytest.mark.parametrize(
    ("periodo", "inicio", "fim"),
    [
        ("DIA", date(2026, 11, 5), date(2026, 11, 5)),
        ("SEMANA", date(2026, 11, 2), date(2026, 11, 8)),
        ("MES", date(2026, 11, 1), date(2026, 11, 30)),
    ],
)
def test_periodo_de(periodo, inicio, fim):
    assert metas.periodo_de(date(2026, 11, 5), periodo) == (inicio, fim)


def test_rotulos():
    assert metas.rotulo_periodo("MES", date(2026, 12, 1)) == "dezembro/2026"
    assert metas.rotulo_periodo("SEMANA", date(2026, 11, 2)) == "semana de 02/11 a 08/11"
    assert metas.moeda(Decimal("1234.5")) == "R$ 1.234,50"


integration = pytest.mark.integration


@pytest.fixture
def metas_db(api_db, criar_usuario_teste):
    api_db.execute(delete(MetaVenda))
    api_db.execute(delete(AlertaConfiguracao))
    api_db.execute(delete(AlertaDestino))
    api_db.execute(delete(Atividade))
    api_db.add(AlertaDestino(nome="Padrão", chat_id=None))
    api_db.flush()
    api_db.info["admin"] = criar_usuario_teste("admin.metas", "ADMIN", modulos=["VENDAS"])
    return api_db


def _dia_com_vendas(db) -> date:
    return db.scalar(select(func.max(Venda.data_venda)))


def _vendido(db, dia: date, *condicoes) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(Venda.valor_total), 0)).where(
            Venda.cancelada.is_(False), Venda.data_venda == dia, *condicoes
        )
    )


@integration
def test_progresso_do_grupo_e_da_loja_no_dia(metas_db):
    admin = metas_db.info["admin"]
    dia = _dia_com_vendas(metas_db)
    loja = metas_db.scalar(select(Empresa).join(Venda).where(Venda.data_venda == dia).limit(1))
    metas.salvar(metas_db, nivel="GRUPO", periodo="DIA", valor=Decimal(1000), usuario=admin)
    metas.salvar(
        metas_db,
        nivel="EMPRESA",
        empresa_id=loja.id,
        periodo="DIA",
        valor=Decimal(500),
        usuario=admin,
    )

    por_nivel = {p.meta.nivel: p for p in metas.progresso(metas_db, dia)}

    assert por_nivel["GRUPO"].realizado == _vendido(metas_db, dia)
    assert por_nivel["EMPRESA"].realizado == _vendido(metas_db, dia, Venda.empresa_id == loja.id)
    assert por_nivel["EMPRESA"].alvo == loja.nome
    grupo = por_nivel["GRUPO"]
    assert grupo.percentual == (grupo.realizado * 100 / 1000).quantize(Decimal("0.1"))


@integration
def test_meta_do_vendedor_soma_as_lojas(metas_db):
    admin = metas_db.info["admin"]
    dia = _dia_com_vendas(metas_db)
    ids = metas_db.scalars(select(Venda.id).where(Venda.data_venda == dia).limit(3)).all()
    metas_db.execute(update(Venda).where(Venda.id.in_(ids)).values(id_vendedor="V9"))
    metas_db.add(Vendedor(id_erp="V9", nome="CAMILA", consultado_em=datetime.now(UTC)))
    metas.salvar(
        metas_db,
        nivel="VENDEDOR",
        id_vendedor="V9",
        periodo="MES",
        valor=Decimal(100),
        usuario=admin,
    )

    [p] = metas.progresso(metas_db, dia)

    assert p.alvo == "CAMILA"
    inicio, fim = metas.periodo_de(dia, "MES")
    assert p.realizado == metas_db.scalar(
        select(func.sum(Venda.valor_total)).where(
            Venda.id_vendedor == "V9", Venda.data_venda.between(inicio, fim)
        )
    )


@integration
def test_meta_de_um_periodo_substitui_a_que_vale_sempre(metas_db):
    admin = metas_db.info["admin"]
    metas.salvar(metas_db, nivel="GRUPO", periodo="MES", valor=Decimal(100), usuario=admin)
    especifica = metas.salvar(
        metas_db,
        nivel="GRUPO",
        periodo="MES",
        valor=Decimal(300),
        usuario=admin,
        referencia=date(2026, 12, 15),
    )
    assert especifica.referencia == date(2026, 12, 1)

    [dezembro] = metas.progresso(metas_db, date(2026, 12, 20))
    [novembro] = metas.progresso(metas_db, date(2026, 11, 20))
    assert dezembro.meta.valor == 300 and novembro.meta.valor == 100

    metas.salvar(metas_db, nivel="GRUPO", periodo="MES", valor=Decimal(150), usuario=admin)
    assert metas_db.scalar(select(func.count()).select_from(MetaVenda)) == 2


@integration
def test_meta_invalida(metas_db):
    admin = metas_db.info["admin"]
    with pytest.raises(metas.MetaInvalida, match="loja"):
        metas.salvar(metas_db, nivel="EMPRESA", periodo="DIA", valor=Decimal(1), usuario=admin)
    with pytest.raises(metas.MetaInvalida, match="maior que zero"):
        metas.salvar(metas_db, nivel="GRUPO", periodo="DIA", valor=Decimal(0), usuario=admin)
    with pytest.raises(metas.MetaInvalida, match="marcos"):
        metas.definir_marcos(metas_db, [], admin)


@integration
def test_aviso_sai_uma_vez_so_e_do_maior_marco(metas_db):
    admin = metas_db.info["admin"]
    dia = _dia_com_vendas(metas_db)
    metas.definir_marcos(metas_db, [50, 100], admin)
    metas.salvar(metas_db, nivel="GRUPO", periodo="DIA", valor=Decimal("0.01"), usuario=admin)
    agora = datetime(dia.year, dia.month, dia.day, 15, tzinfo=TZ)

    assert metas.avaliar_avisos(metas_db, agora, TZ) == 1
    assert metas.avaliar_avisos(metas_db, agora, TZ) == 0

    [aviso] = metas_db.scalars(select(Atividade).where(Atividade.tipo == "meta_atingida")).all()
    assert aviso.resumo == f"Grupo (todas as lojas) bateu a meta do dia {dia:%d/%m}"
    assert aviso.valores["meta"] == "R$ 0,01" and aviso.usuario_nome == "Sistema"

    assert (
        metas_db.scalar(
            select(func.count())
            .select_from(Notificacao)
            .where(Notificacao.atividade_id == aviso.id)
        )
        == 1
    )


@integration
def test_marco_abaixo_de_100_avisa_quanto_falta(metas_db):
    admin = metas_db.info["admin"]
    dia = _dia_com_vendas(metas_db)
    vendido = _vendido(metas_db, dia)
    metas.definir_marcos(metas_db, [50, 100], admin)
    metas.salvar(metas_db, nivel="GRUPO", periodo="DIA", valor=vendido * 15 / 10, usuario=admin)

    metas.avaliar_avisos(metas_db, datetime(dia.year, dia.month, dia.day, 15, tzinfo=TZ), TZ)

    [aviso] = metas_db.scalars(select(Atividade).where(Atividade.tipo == "meta_atingida")).all()
    assert "chegou a 50% da meta do dia" in aviso.resumo
    assert aviso.valores["percentual"] == "67%"


@integration
def test_api_admin_cadastra_e_todos_veem_o_progresso(metas_db, criar_usuario_teste):
    app = app_com_sessao(metas_db)
    admin = TestClient(app, headers=token_para(app, metas_db.info["admin"]))
    operador = criar_usuario_teste("op.metas", "OPERADOR", modulos=["VENDAS"])
    leitor = TestClient(app, headers=token_para(app, operador))

    corpo = {"nivel": "GRUPO", "periodo": "MES", "valor": "250000.00"}
    assert leitor.put("/api/v1/vendas/metas", json=corpo).status_code == 403
    resposta = admin.put("/api/v1/vendas/metas", json=corpo)
    assert resposta.status_code == 200
    [meta] = resposta.json()["metas"]
    assert meta["alvo"] == "Grupo (todas as lojas)" and meta["atualizado_por"] == "Admin.Metas"
    assert resposta.json()["marcos"] == [100]

    progresso = leitor.get("/api/v1/vendas/metas/progresso").json()
    assert [i["meta_id"] for i in progresso["itens"]] == [meta["id"]]

    [alteracao] = metas_db.scalars(
        select(Atividade).where(Atividade.tipo == "metas_alteradas")
    ).all()
    assert alteracao.resumo == (
        "Admin.Metas definiu a meta mensal de Grupo (todas as lojas) em R$ 250.000,00"
    )

    assert admin.put("/api/v1/vendas/metas/marcos", json={"marcos": [0]}).status_code == 422
    assert admin.put("/api/v1/vendas/metas/marcos", json={"marcos": [80, 100]}).json()[
        "marcos"
    ] == [80, 100]
    assert admin.delete(f"/api/v1/vendas/metas/{meta['id']}").status_code == 204
    assert admin.delete(f"/api/v1/vendas/metas/{meta['id']}").status_code == 404
    app.dependency_overrides.clear()
