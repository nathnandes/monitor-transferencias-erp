from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Empresa, NotaMovimento, Produto, Sincronizacao
from app.dominio.operacoes_estoque import CATALOGO, operacao
from app.erp.servicos import ItemNota
from app.sync.estoque import _gravar
from app.sync.movimentos import _gravar_dia
from tests.conftest import app_com_sessao, token_para
from tests.test_api_estoque import _saldo

pytestmark = pytest.mark.integration

URL = "/api/v1/estoque"
AGORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
HOJE = datetime.now(ZoneInfo(get_settings().tz)).date()
ONTEM = HOJE - timedelta(days=1)
ANTEONTEM = HOJE - timedelta(days=2)


def _item(coi: int, planilha: str, qtd: str, valor: str = "10", produto: str = "10") -> ItemNota:
    return ItemNota(
        id_empresa="",
        id_planilha=planilha,
        id_operacao=coi,
        id_produto=produto,
        id_subproduto=produto,
        sequencia="1",
        quantidade=Decimal(qtd),
        descricao_produto=None,
        data_movimento=AGORA,
        valor_liquido=Decimal(valor),
        descricao_operacao=f"OPERACAO {coi}",
    )


def _lado(coi: int) -> bool:
    return (True, coi) in CATALOGO or (False, coi) not in CATALOGO


@pytest.fixture
def livro_db(db_vazio):
    db = db_vazio
    empresas = {}
    for codigo in ("1", "2"):
        empresas[codigo] = Empresa(id_erp=codigo, codigo=codigo, nome=f"Loja {codigo}")
        db.add(empresas[codigo])
    db.add(Produto(id_produto="10", id_subproduto="10", descricao="CIMENTO", sincronizado_em=AGORA))
    execucao = Sincronizacao(tipo="estoque", status="sucesso", inicio=AGORA, fim=AGORA)
    db.add(execucao)
    db.flush()

    _gravar(
        db,
        empresas["1"].id,
        execucao.id,
        [_saldo("10", "30", local="1"), _saldo("10", "20", local="2")],
        AGORA,
    )

    def gravar(codigo: str, dia, *itens: ItemNota) -> None:
        _gravar_dia(
            db,
            empresas[codigo].id,
            dia,
            [(_lado(i.id_operacao), i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )

    gravar("1", ANTEONTEM, _item(11, "C1", "40", "400"), _item(8300, "V1", "5", "50"))

    gravar(
        "1",
        ONTEM,
        _item(8045, "T1", "10", "100"),
        _item(3000, "P1", "3", "30"),
        _item(8007, "A1", "1", "999"),
    )

    gravar("1", HOJE, _item(2000, "B1", "2", "20"), _item(8300, "V2", "7", "70"))

    gravar("2", HOJE, _item(8300, "V9", "1", "15", produto="20"))

    for planilha, saida, hora, usuario in (
        ("V2", True, datetime.combine(HOJE, datetime.min.time(), UTC) + timedelta(hours=15), "ANA"),
        ("C1", False, datetime.combine(ANTEONTEM, datetime.min.time(), UTC), None),
    ):
        db.add(
            NotaMovimento(
                empresa_id=empresas["1"].id,
                id_planilha=planilha,
                saida=saida,
                encontrado=True,
                numero=f"N{planilha}",
                momento=hora,
                usuario=usuario,
                sincronizado_em=AGORA,
            )
        )
    db.flush()
    return db


@pytest.fixture
def api(livro_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.livro", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(livro_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_sinal_e_categoria_do_catalogo():
    assert operacao(True, 8300).fator == -1
    assert operacao(False, 11).fator == 1
    assert operacao(True, 2000).fator == 1

    assert (operacao(True, 3000).categoria, operacao(True, 3000).afeta) == ("venda", False)
    assert operacao(True, 8090).afeta is None
    assert operacao(True, 8007).afeta is False
    novo = operacao(True, 9999)
    assert (novo.categoria, novo.afeta, novo.fator) == ("nao_classificado", None, -1)

    saida = {c for lado, c in CATALOGO if lado}
    entrada = {c for lado, c in CATALOGO if not lado}
    assert not saida & entrada


def test_livro_por_loja_e_coi(api):
    corpo = api.get(f"{URL}/livro", params={"empresa": "1"}).json()

    assert corpo["data_final"] == str(HOJE)
    linhas = {x["coi"]: x for x in corpo["linhas"]}
    assert sorted(linhas) == [11, 2000, 3000, 8007, 8045, 8300]
    venda = linhas[8300]
    assert (venda["categoria"], venda["afeta"], venda["documentos"], venda["itens"]) == (
        "venda",
        True,
        2,
        2,
    )
    assert Decimal(venda["valor"]) == Decimal("-120")
    assert venda["operacao"] == "OPERACAO 8300"
    assert (linhas[3000]["afeta"], linhas[8007]["afeta"]) == (False, False)
    assert linhas[11]["categoria"] == "compra"

    assert corpo["dias_sem_leitura"] == 4

    todas = api.get(f"{URL}/livro").json()
    assert {x["empresa"]["codigo"] for x in todas["linhas"]} == {"1", "2"}


def test_extrato_reconstroi_o_saldo_a_partir_do_atual(api):
    params = {"empresa": "1", "data_inicial": str(ANTEONTEM), "data_final": str(HOJE)}
    corpo = api.get(f"{URL}/10/10/extrato", params=params).json()

    assert corpo["descricao"] == "CIMENTO"

    assert Decimal(corpo["saldo_atual"]) == 50
    assert Decimal(corpo["saldo_final"]) == 50
    assert Decimal(corpo["saldo_inicial"]) == 30
    assert (Decimal(corpo["entradas"]), Decimal(corpo["saidas"])) == (Decimal(42), Decimal(-22))
    saldo_por_dia = {x["dia"]: Decimal(x["saldo_fim_dia"]) for x in corpo["itens"]}
    assert saldo_por_dia == {str(HOJE): 50, str(ONTEM): 55, str(ANTEONTEM): 65}

    assert [x["id_planilha"] for x in corpo["itens"]][:2] == ["V2", "B1"]
    pedido = next(x for x in corpo["itens"] if x["coi"] == 3000)
    assert (pedido["afeta"], Decimal(pedido["quantidade"])) == (False, Decimal(-3))
    assert corpo["dias_sem_leitura"] == []
    assert corpo["total_itens"] == 7


def test_extrato_avisa_dia_sem_leitura(api):
    inicio = HOJE - timedelta(days=4)
    params = {"empresa": "1", "data_inicial": str(inicio), "data_final": str(HOJE)}
    corpo = api.get(f"{URL}/10/10/extrato", params=params).json()

    assert corpo["dias_sem_leitura"] == [str(inicio), str(inicio + timedelta(days=1))]


@pytest.mark.parametrize(
    ("rota", "params"),
    [
        ("/livro", {"empresa": "99"}),
        ("/10/10/extrato", {"empresa": "99"}),
    ],
)
def test_empresa_desconhecida_404(api, rota, params):
    assert api.get(f"{URL}{rota}", params=params).status_code == 404


def test_periodo_grande_demais_422(api):
    params = {"data_inicial": "2024-01-01", "data_final": str(HOJE)}
    assert api.get(f"{URL}/livro", params=params).status_code == 422


def test_extrato_exige_empresa(api):
    assert api.get(f"{URL}/10/10/extrato").status_code == 422


@pytest.mark.parametrize("rota", ["/livro", "/10/10/extrato"])
def test_periodo_que_comeca_depois_de_hoje_422(api, rota):
    params = {
        "empresa": "1",
        "data_inicial": str(HOJE + timedelta(days=30)),
        "data_final": str(HOJE + timedelta(days=35)),
    }
    resposta = api.get(f"{URL}{rota}", params=params)

    assert resposta.status_code == 422
    assert "depois de hoje" in resposta.json()["detail"]


def test_extrato_deixa_os_locais_de_perda_fora_do_saldo(api, monkeypatch):
    from app.database.locais_perda import LocalPerda

    monkeypatch.setattr(
        "app.database.locais_perda.locais_de_perda", lambda: (LocalPerda("1", "2", "Avaria"),)
    )
    params = {"empresa": "1", "data_inicial": str(HOJE), "data_final": str(HOJE)}
    corpo = api.get(f"{URL}/10/10/extrato", params=params).json()

    assert Decimal(corpo["saldo_atual"]) == 30
    assert Decimal(corpo["saldo_final"]) == 30


def test_livro_filtra_por_categoria(api):
    corpo = api.get(f"{URL}/livro", params={"empresa": "1", "categoria": "venda"}).json()

    assert sorted(x["coi"] for x in corpo["linhas"]) == [3000, 8300]


def test_notas_do_livro_com_hora_e_quem_lancou(api):
    corpo = api.get(f"{URL}/livro/notas", params={"empresa": "1"}).json()

    assert corpo["total"] == 7
    notas = {x["id_planilha"]: x for x in corpo["notas"]}
    venda = notas["V2"]
    assert (venda["usuario"], venda["numero"], venda["categoria"], venda["itens"]) == (
        "ANA",
        "NV2",
        "venda",
        1,
    )
    assert venda["momento"].startswith(f"{HOJE}T15:00:00")
    assert Decimal(venda["valor"]) == Decimal("-70")
    assert (notas["C1"]["usuario"], notas["C1"]["momento"] is not None) == (None, True)

    assert (notas["B1"]["momento"], notas["B1"]["usuario"], notas["B1"]["dia"]) == (
        None,
        None,
        str(HOJE),
    )

    ordem = [x["id_planilha"] for x in corpo["notas"]]
    assert ordem[0] == "V2"
    assert ordem.index("B1") < ordem.index("T1") < ordem.index("C1")


@pytest.mark.parametrize(
    ("params", "esperado"),
    [
        ({"categoria": "venda"}, {"V1", "V2", "P1", "V9"}),
        ({"categoria": "compra"}, {"C1"}),
        ({"coi": 8300, "empresa": "2"}, {"V9"}),
    ],
)
def test_notas_do_livro_filtram_por_categoria_e_coi(api, params, esperado):
    corpo = api.get(f"{URL}/livro/notas", params=params).json()

    assert {x["id_planilha"] for x in corpo["notas"]} == esperado


def test_notas_do_livro_paginam(api):
    corpo = api.get(f"{URL}/livro/notas", params={"tamanho_pagina": 3, "pagina": 3}).json()

    assert (corpo["total"], corpo["total_paginas"], len(corpo["notas"])) == (8, 3, 2)


def test_produtos_da_nota(api):
    itens = api.get(f"{URL}/livro/notas/1/V2").json()

    assert [(x["id_produto"], x["descricao"]) for x in itens] == [("10", "CIMENTO")]
    assert Decimal(itens[0]["quantidade"]) == Decimal(-7)


@pytest.mark.parametrize("rota", ["/livro/notas/1/NAOEXISTE", "/livro/notas/99/V2"])
def test_produtos_da_nota_desconhecida_404(api, rota):
    assert api.get(f"{URL}{rota}").status_code == 404
