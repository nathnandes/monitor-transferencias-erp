from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Empresa, Produto, Sincronizacao
from app.erp.servicos import ItemNota
from app.sync.movimentos import _gravar_dia
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

URL = "/api/v1/estoque/movimentos"
AGORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

HOJE = datetime.now(ZoneInfo(get_settings().tz)).date()
ONTEM = HOJE - timedelta(days=1)
H, D1 = HOJE.isoformat(), ONTEM.isoformat()


def _item(coi: int, planilha: str, produto: str, qtd: str, valor: str, seq: str = "1") -> ItemNota:
    return ItemNota(
        id_empresa="",
        id_planilha=planilha,
        id_operacao=coi,
        id_produto=produto,
        id_subproduto=produto,
        sequencia=seq,
        quantidade=Decimal(qtd),
        descricao_produto=None if coi == 80 else f"ITEM {produto}",
        data_movimento=AGORA,
        valor_liquido=Decimal(valor),
    )


@pytest.fixture
def movimentos_db(db_vazio):
    db = db_vazio
    empresas = {}
    for codigo in ("1", "2"):
        empresas[codigo] = Empresa(id_erp=codigo, codigo=codigo, nome=f"Loja {codigo}")
        db.add(empresas[codigo])
    db.add(
        Produto(id_produto="10", id_subproduto="10", descricao="CADASTRO 10", sincronizado_em=AGORA)
    )
    db.flush()

    def gravar(codigo: str, dia: date, *itens: ItemNota) -> None:
        _gravar_dia(
            db,
            empresas[codigo].id,
            dia,
            [(i.id_operacao != 80, i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )

    gravar("1", ONTEM, _item(80, "E1", "10", "5", "50"), _item(8080, "S1", "20", "2", "30"))

    gravar(
        "1",
        HOJE,
        _item(2000, "B1", "10", "-3", "-30", "1"),
        _item(2000, "B1", "20", "1", "15", "2"),
        _item(2000, "B1", "30", "4", "8", "10"),
    )

    gravar("2", HOJE, _item(8080, "S9", "10", "1", "10"), _item(8300, "V1", "10", "7", "70"))
    db.add(
        Sincronizacao(
            tipo="movimentos_estoque",
            inicio=AGORA - timedelta(minutes=1),
            fim=AGORA,
            status="sucesso",
        )
    )
    db.flush()
    return db


@pytest.fixture
def api_movimentos(movimentos_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.movimentos", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(movimentos_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_sem_token_401(client):
    assert client.get(URL).status_code == 401


def test_sem_modulo_estoque_403(db_vazio, criar_usuario_teste):
    usuario = criar_usuario_teste("so.vendas", "OPERADOR", modulos=["VENDAS"])
    app = app_com_sessao(db_vazio)
    resposta = TestClient(app, headers=token_para(app, usuario)).get(URL)
    app.dependency_overrides.clear()
    assert resposta.status_code == 403


def test_lista_do_mais_recente_com_o_sinal_do_efeito(api_movimentos):
    resposta = api_movimentos.get(URL)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 6
    assert corpo["total_paginas"] == 1
    linhas = [
        (i["dia"], i["empresa"]["codigo"], i["tipo"], i["id_produto"], i["quantidade"])
        for i in corpo["itens"]
    ]
    assert linhas == [
        (H, "1", "balanco", "10", "-3.0000"),
        (H, "1", "balanco", "20", "1.0000"),
        (H, "1", "balanco", "30", "4.0000"),
        (H, "2", "saida_avulsa", "10", "-1.0000"),
        (D1, "1", "entrada_avulsa", "10", "5.0000"),
        (D1, "1", "saida_avulsa", "20", "-2.0000"),
    ]
    entrada = corpo["itens"][4]
    assert entrada["coi"] == 80
    assert entrada["valor"] == "50.0000"
    assert entrada["descricao"] == "CADASTRO 10"
    assert corpo["itens"][5]["descricao"] == "ITEM 20"
    assert corpo["cobertura"] == {
        "desde": D1,
        "ate": H,
        "atualizado_em": "2026-10-17T12:00:00Z",
    }
    assert corpo["filtro"]["data_inicial"] == (HOJE - timedelta(days=6)).isoformat()


def test_resumo_por_empresa_dia_e_tipo_com_falta_e_sobra_do_balanco(api_movimentos):
    resumo = api_movimentos.get(URL).json()["resumo"]

    chaves = [(r["dia"], r["empresa"]["codigo"], r["tipo"]) for r in resumo]
    assert chaves == [
        (H, "1", "balanco"),
        (H, "2", "saida_avulsa"),
        (D1, "1", "entrada_avulsa"),
        (D1, "1", "saida_avulsa"),
    ]
    balanco = resumo[0]
    assert balanco["itens"] == 3
    assert Decimal(balanco["quantidade"]) == Decimal("2")
    assert Decimal(balanco["valor"]) == Decimal("-7")
    assert balanco["falta_itens"] == 1
    assert Decimal(balanco["falta_quantidade"]) == Decimal("-3")
    assert Decimal(balanco["falta_valor"]) == Decimal("-30")
    assert balanco["sobra_itens"] == 2
    assert Decimal(balanco["sobra_quantidade"]) == Decimal("5")
    assert Decimal(balanco["sobra_valor"]) == Decimal("23")
    saida = resumo[1]
    assert saida["itens"] == 1
    assert Decimal(saida["valor"]) == Decimal("-10")
    assert saida["falta_itens"] is None
    assert saida["sobra_valor"] is None


def test_filtros_de_periodo_empresa_tipo_e_produto(api_movimentos):
    ontem = api_movimentos.get(URL, params={"data_inicial": ONTEM, "data_final": ONTEM}).json()
    assert ontem["total"] == 2
    assert ontem["filtro"]["data_final"] == D1
    assert {r["dia"] for r in ontem["resumo"]} == {D1}

    loja2 = api_movimentos.get(URL, params={"empresa": "2"}).json()
    assert [i["id_planilha"] for i in loja2["itens"]] == ["S9"]
    assert loja2["filtro"]["empresa"]["nome"] == "Loja 2"

    balancos = api_movimentos.get(URL, params={"tipo": "balanco"}).json()
    assert balancos["total"] == 3
    assert [r["tipo"] for r in balancos["resumo"]] == ["balanco"]

    produto = api_movimentos.get(URL, params={"produto": "10", "subproduto": "10"}).json()
    assert [(i["empresa"]["codigo"], i["tipo"]) for i in produto["itens"]] == [
        ("1", "balanco"),
        ("2", "saida_avulsa"),
        ("1", "entrada_avulsa"),
    ]
    assert produto["filtro"]["produto"] == "10"


def test_paginacao(api_movimentos):
    corpo = api_movimentos.get(URL, params={"tamanho_pagina": 4, "pagina": 2}).json()
    assert corpo["total"] == 6
    assert corpo["total_paginas"] == 2
    assert [i["id_planilha"] for i in corpo["itens"]] == ["E1", "S1"]
    assert len(corpo["resumo"]) == 4


def test_intervalo_pela_metade_422(api_movimentos):
    resposta = api_movimentos.get(URL, params={"data_inicial": ONTEM})
    assert resposta.status_code == 422


def test_tipo_invalido_422(api_movimentos):
    assert api_movimentos.get(URL, params={"tipo": "venda"}).status_code == 422


def test_empresa_desconhecida_404(api_movimentos):
    assert api_movimentos.get(URL, params={"empresa": "99"}).status_code == 404


def test_banco_vazio(db_vazio, criar_usuario_teste):
    usuario = criar_usuario_teste("op.vazio", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db_vazio)
    corpo = TestClient(app, headers=token_para(app, usuario)).get(URL).json()
    app.dependency_overrides.clear()
    assert corpo["total"] == 0
    assert corpo["itens"] == []
    assert corpo["resumo"] == []
    assert corpo["cobertura"] == {"desde": None, "ate": None, "atualizado_em": None}


def test_filtro_avulsas_traz_entrada_e_saida_sem_o_balanco(api_movimentos):
    corpo = api_movimentos.get(URL, params={"tipo": "avulsas"}).json()

    assert sorted(i["id_planilha"] for i in corpo["itens"]) == ["E1", "S1", "S9"]
    assert corpo["filtro"]["tipo"] == "avulsas"
    assert {r["tipo"] for r in corpo["resumo"]} == {"entrada_avulsa", "saida_avulsa"}


def test_sem_periodo_lista_so_os_ultimos_7_dias(movimentos_db, api_movimentos):
    um = movimentos_db.query(Empresa).filter_by(codigo="1").one()
    antigo = HOJE - timedelta(days=10)
    _gravar_dia(
        movimentos_db,
        um.id,
        antigo,
        [(True, _item(8080, "VELHO", "10", "1", "10"))],
        completo=True,
        execucao_id=None,
        momento=AGORA,
    )
    movimentos_db.flush()

    corpo = api_movimentos.get(URL).json()

    assert "VELHO" not in {i["id_planilha"] for i in corpo["itens"]}
    assert antigo.isoformat() not in {r["dia"] for r in corpo["resumo"]}
    assert (corpo["filtro"]["data_inicial"], corpo["filtro"]["data_final"]) == (
        (HOJE - timedelta(days=6)).isoformat(),
        H,
    )
    pedido = {"data_inicial": antigo.isoformat(), "data_final": antigo.isoformat()}
    assert api_movimentos.get(URL, params=pedido).json()["total"] == 1


def test_periodo_acima_do_maximo_422(api_movimentos):
    pedido = {"data_inicial": (HOJE - timedelta(days=400)).isoformat(), "data_final": H}
    assert api_movimentos.get(URL, params=pedido).status_code == 422
