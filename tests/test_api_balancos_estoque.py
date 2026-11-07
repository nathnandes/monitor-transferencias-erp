from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.database.models import Empresa, MovimentoEstoque, PrecoProdutoEmpresa, Produto
from app.erp.servicos import ItemNota
from app.sync.movimentos import _gravar_dia
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

URL = "/api/v1/estoque/balancos"
AGORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
DIA = date(2026, 10, 10)
PERIODO = {"data_inicial": "2026-10-01", "data_final": "2026-10-17"}


def _item(coi: int, planilha: str, produto: str, qtd: str, valor: str, seq: str) -> ItemNota:
    return ItemNota(
        id_empresa="",
        id_planilha=planilha,
        id_operacao=coi,
        id_produto=produto,
        id_subproduto=produto,
        sequencia=seq,
        quantidade=Decimal(qtd),
        descricao_produto=None,
        data_movimento=AGORA,
        valor_liquido=Decimal(valor),
    )


@pytest.fixture
def api(db_vazio, criar_usuario_teste):
    db = db_vazio
    empresas = {}
    for codigo in ("1", "2"):
        empresas[codigo] = Empresa(id_erp=codigo, codigo=codigo, nome=f"Loja {codigo}")
        db.add(empresas[codigo])
    db.flush()

    def gravar(codigo, dia, *itens):
        _gravar_dia(
            db,
            empresas[codigo].id,
            dia,
            [(True, i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )

    gravar(
        "1",
        DIA,
        _item(2000, "B1", "10", "-10", "-100", "1"),
        _item(2000, "B1", "20", "-5", "-50", "2"),
        _item(2000, "B1", "20", "5", "50", "3"),
        _item(2000, "B1", "30", "2", "40", "4"),
        _item(2000, "B1", "40", "-3", "-30", "5"),
        _item(2000, "B1", "40", "1", "20", "6"),
        _item(2000, "B1", "50", "-2", "0", "7"),
        _item(2000, "B1", "60", "0", "-999", "8"),
        _item(2000, "B1", "70", "-8", "-800", "9"),
        _item(2000, "B1", "80", "9", "900", "10"),
        _item(8080, "S1", "10", "50", "500", "1"),
    )
    db.execute(
        update(MovimentoEstoque)
        .where(MovimentoEstoque.id_produto == "70")
        .values(descricao_produto="CAIXA * USO INTERNO")
    )
    db.add(Produto(id_produto="80", id_subproduto="80", descricao="*BRINDE", sincronizado_em=AGORA))

    gravar("2", date(2026, 10, 12), _item(2000, "B3", "70", "8", "800", "1"))
    db.add(
        PrecoProdutoEmpresa(
            empresa_id=empresas["1"].id,
            id_produto="50",
            id_subproduto="50",
            custo_gerencial=Decimal(7),
            sincronizado_em=AGORA,
        )
    )

    gravar("2", date(2026, 10, 12), _item(2000, "B2", "10", "4", "40", "1"))
    db.flush()
    operador = criar_usuario_teste("op.balanco", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_perda_e_ganho_item_a_item_como_o_erp_poder(api):
    corpo = api.get(URL, params=PERIODO).json()

    t = corpo["totais"]

    assert (Decimal(t["perda"]), Decimal(t["ganho"]), Decimal(t["resultado"])) == (
        Decimal("-180"),
        Decimal("150"),
        Decimal("-30"),
    )

    assert (t["produtos_com_falta"], t["produtos_com_sobra"], t["balancos"]) == (3, 2, 2)
    assert t["itens"] == 8
    lojas = {x["empresa"]["codigo"]: Decimal(x["resultado"]) for x in corpo["por_loja"]}
    assert lojas == {"1": Decimal("-70"), "2": Decimal("40")}
    assert [x["id_produto"] for x in corpo["maiores_perdas"]] == ["10", "40"]
    assert Decimal(corpo["maiores_perdas"][1]["valor"]) == Decimal("-10")
    eventos = {(e["empresa"]["codigo"], e["dia"]): e for e in corpo["eventos"]}
    assert set(eventos) == {("1", "2026-10-10"), ("2", "2026-10-12")}
    assert Decimal(eventos[("1", "2026-10-10")]["falta_valor"]) == Decimal("-180")


def test_falta_numa_loja_e_sobra_noutra_e_transferencia_provavel(api):
    corpo = api.get(URL, params=PERIODO).json()

    [par] = corpo["transferencias_provaveis"]
    assert (par["id_produto"], par["loja_falta"]["codigo"], par["loja_sobra"]["codigo"]) == (
        "10",
        "1",
        "2",
    )
    assert (Decimal(par["quantidade"]), Decimal(par["valor"])) == (Decimal(4), Decimal(40))
    assert Decimal(corpo["valor_transferencias_provaveis"]) == Decimal(40)

    so_dois = api.get(URL, params={**PERIODO, "empresa": "2"}).json()
    assert len(so_dois["transferencias_provaveis"]) == 1
    assert Decimal(so_dois["totais"]["perda"]) == 0


def test_sem_balanco_no_periodo(api):
    corpo = api.get(URL, params={"data_inicial": "2026-09-01", "data_final": "2026-09-30"}).json()
    assert corpo["totais"]["balancos"] == 0
    assert corpo["por_loja"] == [] and corpo["transferencias_provaveis"] == []


@pytest.fixture
def api_recontagens(db_vazio, criar_usuario_teste):
    db = db_vazio
    loja = Empresa(id_erp="1", codigo="1", nome="Loja 1")
    db.add(loja)
    db.flush()

    def gravar(dia, *itens):
        _gravar_dia(
            db,
            loja.id,
            dia,
            [(True, i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )

    gravar(
        date(2026, 10, 1),
        _item(2000, "R1", "10", "-1", "-10", "1"),
        _item(2000, "R1", "20", "2", "20", "2"),
        _item(2000, "R1", "30", "-1", "-10", "3"),
    )
    gravar(
        date(2026, 10, 5),
        _item(2000, "R2", "10", "-1", "-10", "1"),
        _item(2000, "R2", "20", "-1", "-10", "2"),
    )
    gravar(
        date(2026, 10, 9),
        _item(2000, "R3", "10", "1", "10", "1"),
        _item(2000, "R3", "40", "-3", "-30", "2"),
        _item(2000, "R3", "40", "3", "30", "3"),
    )
    for produto, marca in (("10", "TIGRE"), ("20", " 3M "), ("40", "TIGRE")):
        db.add(
            Produto(id_produto=produto, id_subproduto=produto, marca=marca, sincronizado_em=AGORA)
        )
    db.flush()
    operador = criar_usuario_teste("op.recontagem", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_recontagens_mais_de_n_balancos(api_recontagens):
    corpo = api_recontagens.get(f"{URL}/recontagens", params=PERIODO).json()

    assert [(x["id_produto"], x["contagens"]) for x in corpo["itens"]] == [("10", 3), ("20", 2)]
    assert corpo["itens"][0]["dias"] == ["2026-10-01", "2026-10-05", "2026-10-09"]
    assert (Decimal(corpo["itens"][0]["quantidade"]), Decimal(corpo["itens"][0]["valor"])) == (
        Decimal(-1),
        Decimal(-10),
    )
    assert corpo["total"] == 2

    so_tres = api_recontagens.get(f"{URL}/recontagens", params={**PERIODO, "mais_de": 2}).json()
    assert [x["id_produto"] for x in so_tres["itens"]] == ["10"]


def test_recontados_a_partir_de_um_dia(api_recontagens):
    corpo = api_recontagens.get(
        f"{URL}/recontagens", params={**PERIODO, "desde": "2026-10-06"}
    ).json()

    assert [x["id_produto"] for x in corpo["itens"]] == ["10"]
    assert corpo["desde"] == "2026-10-06"


def test_recontagens_por_uma_ou_mais_marcas(api_recontagens):
    url = f"{URL}/recontagens"
    corpo = api_recontagens.get(url, params=PERIODO).json()

    assert corpo["marcas"] == [{"marca": "3M", "produtos": 1}, {"marca": "TIGRE", "produtos": 1}]
    assert [x["marca"] for x in corpo["itens"]] == ["TIGRE", "3M"]

    so_tigre = api_recontagens.get(url, params={**PERIODO, "marca": "TIGRE"}).json()
    assert [x["id_produto"] for x in so_tigre["itens"]] == ["10"]
    assert so_tigre["total"] == 1

    assert len(so_tigre["marcas"]) == 2

    duas = api_recontagens.get(url, params={**PERIODO, "marca": ["TIGRE", "3M"]}).json()
    assert [x["id_produto"] for x in duas["itens"]] == ["10", "20"]
