from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import (
    Empresa,
    MovimentoEstoque,
    MovimentoEstoqueDia,
    Produto,
    Sincronizacao,
    Venda,
    VendaDia,
    VendaItem,
)
from app.services.estoque import STATUS_COBERTURA, classificar_cobertura
from app.sync.estoque import _gravar, recalcular_estoque_consolidado
from tests.conftest import app_com_sessao, token_para
from tests.sync_fakes import fabrica_de
from tests.test_api_estoque import _saldo

pytestmark = pytest.mark.integration

URL = "/api/v1/estoque"
AGORA = datetime(2026, 10, 7, 18, 0, tzinfo=UTC)
HOJE = datetime.now(ZoneInfo(get_settings().tz)).date()
JANELA = {"janela_dias": 10}
_NOTAS = count(1)


def _vender(db, empresa, dia, *itens, cancelada=False):
    venda = Venda(
        empresa_id=empresa.id,
        id_erp=str(next(_NOTAS)),
        coi=8300,
        canal="balcao",
        data_venda=dia,
        cancelada=cancelada,
        valor_total=Decimal(0),
        valor_desconto=Decimal(0),
        quantidade_itens=len(itens),
        sincronizado_em=AGORA,
        itens=[VendaItem(id_produto=p, id_subproduto=p, quantidade=Decimal(q)) for p, q in itens],
    )
    db.add(venda)


@pytest.fixture
def cobertura_db(db_vazio):
    db = db_vazio
    empresas = {}
    for codigo, ativo in (("1", True), ("2", True), ("4", True), ("9", False)):
        empresas[codigo] = Empresa(id_erp=codigo, codigo=codigo, nome=f"Loja {codigo}", ativo=ativo)
        db.add(empresas[codigo])
    execucao = Sincronizacao(tipo="estoque", status="sucesso", inicio=AGORA, fim=AGORA)
    db.add(execucao)
    db.flush()

    dados = {
        "1": [
            _saldo("1", "0"),
            _saldo("2", "10"),
            _saldo("3", "24"),
            _saldo("4", "1000"),
            _saldo("5", "7"),
            _saldo("6", "0"),
        ],
        "2": [_saldo("2", "8")],
        "4": [_saldo("1", "50")],
        "9": [_saldo("2", "0")],
    }
    for codigo, saldos in dados.items():
        _gravar(db, empresas[codigo].id, execucao.id, saldos, AGORA)

    ontem = HOJE - timedelta(days=1)
    for n in range(1, 11):
        dia = HOJE - timedelta(days=n)
        for codigo in ("1", "4"):
            notas = 1 if codigo == "1" and n == 1 else 0
            db.add(
                VendaDia(
                    empresa_id=empresas[codigo].id, dia=dia, notas=notas, sincronizado_em=AGORA
                )
            )
    for n in range(1, 6):
        dia = HOJE - timedelta(days=n)
        db.add(VendaDia(empresa_id=empresas["2"].id, dia=dia, notas=1, sincronizado_em=AGORA))

    db.add(VendaDia(empresa_id=empresas["9"].id, dia=ontem, notas=1, sincronizado_em=AGORA))
    _vender(db, empresas["9"], ontem, ("2", "500"))

    loja1 = empresas["1"]
    _vender(db, loja1, ontem, ("1", "12"), ("2", "20"), ("3", "20"))
    _vender(db, loja1, HOJE - timedelta(days=10), ("1", "8"), ("4", "10"))
    _vender(db, loja1, ontem, ("3", "1000"), cancelada=True)
    _vender(db, loja1, HOJE, ("2", "1000"))
    _vender(db, loja1, HOJE - timedelta(days=11), ("5", "1000"))
    _vender(db, empresas["2"], ontem, ("2", "10"))
    db.flush()
    recalcular_estoque_consolidado(
        fabrica_de(db), ambiente="producao", empresas=("1", "2", "4"), agora=lambda: AGORA
    )
    return db


@pytest.fixture
def api(cobertura_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.cobertura", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(cobertura_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def _cobertura(corpo):
    return {
        i["id_produto"]: (i["venda_media_diaria"], i["cobertura_dias"], i["status_cobertura"])
        for i in corpo["itens"]
    }


def test_consolidado_soma_estoque_e_vendas_da_rede(api):
    corpo = api.get(URL, params=JANELA).json()

    assert corpo["janela"] == {
        "inicio": str(HOJE - timedelta(days=10)),
        "fim": str(HOJE - timedelta(days=1)),
        "dias": 10,
    }
    assert corpo["tem_vendas"] is True
    cobertura = _cobertura(corpo)
    media_1, dias_1, status_1 = cobertura["1"]
    assert (Decimal(media_1), dias_1, status_1) == (Decimal(2), "25.0", "adequada")

    assert Decimal(cobertura["2"][0]) == 4
    assert cobertura["2"][1:] == ("4.5", "critica")
    assert cobertura["3"][1:] == ("12.0", "baixa")
    assert cobertura["4"][1:] == ("1000.0", "excesso")
    assert cobertura["5"] == (None, None, "sem_giro")
    assert cobertura["6"] == (None, None, None)


def test_por_empresa_mostra_a_ruptura_da_loja(api):
    corpo = api.get(URL, params={**JANELA, "empresa": "1"}).json()

    cobertura = _cobertura(corpo)
    assert cobertura["1"][1:] == ("0.0", "ruptura")
    assert cobertura["2"][1:] == ("5.0", "critica")


def test_deposito_sem_vendas_fica_sem_cobertura(api):
    corpo = api.get(URL, params={**JANELA, "empresa": "4"}).json()

    assert corpo["tem_vendas"] is False
    assert _cobertura(corpo) == {"1": (None, None, None)}
    resumo = api.get(f"{URL}/cobertura", params={**JANELA, "empresa": "4"}).json()
    assert resumo["tem_vendas"] is False
    assert set(resumo["produtos"].values()) == {0}


def test_filtro_e_ordem_por_cobertura(api):
    params = {**JANELA, "empresa": "1", "ordenacao": "menor_cobertura"}
    corpo = api.get(URL, params=params).json()

    assert [i["id_produto"] for i in corpo["itens"]] == ["1", "2", "3", "4", "5", "6"]

    corpo = api.get(URL, params={**params, "cobertura": "ruptura"}).json()
    assert corpo["total"] == 1
    assert corpo["itens"][0]["id_produto"] == "1"


def test_resumo_conta_por_classificacao(api):
    rede = api.get(f"{URL}/cobertura", params=JANELA).json()
    assert rede["produtos"] == {
        "ruptura": 0,
        "critica": 1,
        "baixa": 1,
        "adequada": 1,
        "excesso": 1,
        "sem_giro": 1,
    }
    loja = api.get(f"{URL}/cobertura", params={**JANELA, "empresa": "1"}).json()
    assert loja["produtos"]["ruptura"] == 1
    assert loja["produtos"]["adequada"] == 0


def test_detalhe_traz_cobertura_por_empresa(api):
    corpo = api.get(f"{URL}/1/1", params=JANELA).json()

    assert (corpo["cobertura_dias"], corpo["status_cobertura"]) == ("25.0", "adequada")
    por_empresa = {
        e["empresa"]["codigo"]: (e["venda_media_diaria"], e["status_cobertura"])
        for e in corpo["empresas"]
    }
    assert Decimal(por_empresa["1"][0]) == 2
    assert por_empresa["1"][1] == "ruptura"
    assert por_empresa["4"] == (None, None)


def test_exportacao_traz_as_colunas_de_cobertura(api):
    resposta = api.get(f"{URL}/exportar", params={**JANELA, "empresa": "1", "produto": "2"})

    texto = resposta.content.decode("utf-8-sig")
    assert "Venda média/dia (10 dias)" in texto
    assert "Crítica" in texto


def _mover(db, empresa, dia, coi, tipo, produto, quantidade):
    db.add(
        MovimentoEstoque(
            empresa_id=empresa.id,
            dia=dia,
            coi=coi,
            tipo=tipo,
            id_planilha=str(next(_NOTAS)),
            id_produto=produto,
            id_subproduto=produto,
            quantidade=Decimal(quantidade),
            sincronizado_em=AGORA,
        )
    )


@pytest.fixture
def api_locais(api, cobertura_db, monkeypatch):
    monkeypatch.setattr(get_settings(), "estoque_locais_somados", "1:1=8")
    db = cobertura_db
    loja1 = db.query(Empresa).filter_by(codigo="1").one()
    execucao = db.query(Sincronizacao).filter_by(tipo="estoque").one()
    saldos = [_saldo("2", "6", local="8"), _saldo("2", "4", local="3")]
    _gravar(db, loja1.id, execucao.id, saldos, AGORA)
    fuso = ZoneInfo(get_settings().tz)
    validos = [HOJE - timedelta(days=n) for n in range(4, 12) if n != 11] + [
        HOJE - timedelta(days=2)
    ]
    for n in range(1, 11):
        dia = HOJE - timedelta(days=n)
        lido = datetime.combine(dia, time(12), fuso) if n == 3 else datetime.now(UTC)
        db.add(
            MovimentoEstoqueDia(
                empresa_id=loja1.id, dia=dia, movimentos=1, versao=2, sincronizado_em=lido
            )
        )
    for dia in validos:
        for produto in ("1", "2", "3"):
            _mover(db, loja1, dia, 8300, "venda", produto, "-2")
        _mover(db, loja1, dia, 3001, "venda", "4", "-1")
        _mover(db, loja1, dia, 3000, "venda", "4", "-1000")
        _mover(db, loja1, dia, 31, "devolucao_venda", "3", "1")
    _mover(db, loja1, HOJE - timedelta(days=3), 8300, "venda", "1", "-500")
    db.flush()
    return api


def _zerada(**contagem):
    return {s: contagem.get(s, 0) for s in STATUS_COBERTURA}


def test_cobertura_das_lojas_pela_baixa_do_estoque_por_empresa_e_local(api_locais, cobertura_db):
    corpo = api_locais.get(f"{URL}/cobertura/lojas", params=JANELA).json()

    assert corpo["janela"]["dias"] == 10
    empresas = {e["empresa"]["codigo"]: e for e in corpo["empresas"]}
    assert list(empresas) == ["1", "2", "4"]
    loja1 = empresas["1"]
    assert loja1["tem_vendas"] is True

    assert loja1["produtos"] == _zerada(ruptura=1, adequada=1, excesso=1, sem_giro=1)
    locais = {x["id_local"]: x for x in loja1["locais"]}

    assert list(locais) == ["1", "3"]
    assert locais["1"]["somados"] == [{"id_local": "8", "descricao": "LOCAL 8"}]
    assert locais["1"]["descricao"] == "LOCAL 1"

    assert locais["1"]["produtos"] == _zerada(ruptura=1, adequada=1, excesso=1, sem_giro=1)
    assert locais["1"]["produtos_com_saldo"] == 4
    assert locais["3"]["produtos"] == _zerada()
    assert locais["3"]["produtos_com_saldo"] == 1
    assert locais["3"]["somados"] == []

    assert empresas["2"]["tem_vendas"] is False

    assert empresas["4"]["tem_vendas"] is False
    assert empresas["4"]["produtos"] == _zerada()
    assert empresas["4"]["locais"][0]["produtos_com_saldo"] == 1
    assert empresas["4"]["locais"][0]["produtos"] == _zerada()


def test_falta_que_nenhum_deposito_tem_fica_fora_da_aba_loja(api_locais, cobertura_db):
    params = {**JANELA, "empresa": "1", "cobertura": "baixa", "media": "baixa"}
    lista = api_locais.get(URL, params={**params, "so_locais_da_loja": True}).json()
    assert lista["total"] == 0

    assert [i["id_produto"] for i in api_locais.get(URL, params=params).json()["itens"]] == ["2"]

    deposito4 = cobertura_db.query(Empresa).filter_by(codigo="4").one()
    execucao = cobertura_db.query(Sincronizacao).filter_by(tipo="estoque").one()
    _gravar(cobertura_db, deposito4.id, execucao.id, [_saldo("1", "50"), _saldo("2", "5")], AGORA)
    cobertura_db.flush()
    lojas = api_locais.get(f"{URL}/cobertura/lojas", params=JANELA).json()
    loja1 = next(e for e in lojas["empresas"] if e["empresa"]["codigo"] == "1")
    assert loja1["produtos"]["baixa"] == 1
    assert {x["id_local"]: x["produtos"]["critica"] for x in loja1["locais"]} == {"1": 0, "3": 1}
    lista = api_locais.get(URL, params={**params, "so_locais_da_loja": True}).json()
    assert [i["id_produto"] for i in lista["itens"]] == ["2"]


def test_lista_e_contagem_de_um_local_pela_baixa(api_locais):
    params = {**JANELA, "empresa": "1", "local": "3", "media": "baixa"}
    corpo = api_locais.get(URL, params=params).json()
    assert _cobertura(corpo) == {"2": ("2.000", "2.0", "critica")}

    params = {**JANELA, "empresa": "1", "local": "1", "media": "baixa"}
    corpo = api_locais.get(URL, params={**params, "produto": "2"}).json()
    assert corpo["itens"][0]["saldo_atual"] == "16.000"
    assert _cobertura(corpo) == {"2": ("2.000", "8.0", "baixa")}
    resumo = api_locais.get(f"{URL}/cobertura", params=params)
    assert resumo.json()["produtos"] == _zerada(
        ruptura=1, baixa=1, adequada=1, excesso=1, sem_giro=1
    )

    resumo = api_locais.get(f"{URL}/cobertura", params={**params, "media": "vendas"})
    assert resumo.json()["produtos"]["baixa"] == 2


def test_locais_fora_da_loja_ficam_fora_da_aba(api_locais, monkeypatch):

    monkeypatch.setattr(get_settings(), "estoque_locais_fora_da_loja", "trocas, local 3")
    corpo = api_locais.get(f"{URL}/cobertura/lojas", params=JANELA).json()
    loja1 = next(e for e in corpo["empresas"] if e["empresa"]["codigo"] == "1")
    assert [x["id_local"] for x in loja1["locais"]] == ["1"]
    assert loja1["desconsiderados"] == [{"id_local": "3", "descricao": "LOCAL 3"}]

    params = {**JANELA, "empresa": "1", "produto": "2", "media": "baixa"}
    corpo = api_locais.get(URL, params={**params, "so_locais_da_loja": True}).json()
    assert corpo["itens"][0]["saldo_atual"] == "16.000"

    assert api_locais.get(URL, params=params).json()["itens"][0]["saldo_atual"] == "20.000"


def test_pedido_de_abastecimento_por_deposito(api_locais, cobertura_db):
    db = cobertura_db
    deposito5 = Empresa(id_erp="5", codigo="5", nome="Loja 5", ativo=True)
    db.add(deposito5)
    db.flush()
    execucao = db.query(Sincronizacao).filter_by(tipo="estoque").one()
    _gravar(db, deposito5.id, execucao.id, [_saldo("1", "30")], AGORA)
    _cadastrar(db, ("1", "1"), ("2", "2"))
    db.query(Produto).filter_by(id_produto="1").update({"marca": "TIGRE"})
    db.flush()

    params = {**JANELA, "loja": "1"}
    corpo = api_locais.get(f"{URL}/pedido-abastecimento", params=params).json()
    assert (corpo["alvo_dias"], corpo["tem_vendas"]) == (30, True)
    pedidos = {p["deposito"]["codigo"]: p["itens"] for p in corpo["pedidos"]}
    assert list(pedidos) == ["4", "5"]
    [do4] = pedidos["4"]
    assert (do4["id_subproduto"], do4["marca"], do4["status_cobertura"]) == (
        "1",
        "TIGRE",
        "ruptura",
    )
    assert (do4["necessidade"], do4["quantidade"], do4["disponivel_deposito"]) == (
        "60.000",
        "50.000",
        "50.000",
    )
    assert [(i["id_subproduto"], i["quantidade"]) for i in pedidos["5"]] == [("1", "10.000")]
    assert [(i["id_subproduto"], i["necessidade"]) for i in corpo["sem_estoque"]] == [
        ("2", "40.000")
    ]

    corpo = api_locais.get(f"{URL}/pedido-abastecimento", params={**params, "alvo_dias": 20}).json()
    assert [len(p["itens"]) for p in corpo["pedidos"]] == [1, 0]

    api_locais.post(f"{URL}/excecoes", json={"empresa": "1", "codigo": "2"})
    corpo = api_locais.get(f"{URL}/pedido-abastecimento", params=params).json()
    assert corpo["sem_estoque"] == []

    arquivo = api_locais.get(
        f"{URL}/pedido-abastecimento/exportar", params={**params, "deposito": "5"}
    )
    assert arquivo.status_code == 200
    linhas = arquivo.content.decode("utf-8-sig").splitlines()
    assert linhas[0].startswith("Marca;Produto;Subproduto;Descrição;Quantidade")
    assert linhas[1].startswith("TIGRE;1;1;ITEM 1;10")
    assert (
        api_locais.get(
            f"{URL}/pedido-abastecimento/exportar", params={**params, "deposito": "2"}
        ).status_code
        == 404
    )


def test_pedido_de_loja_sem_baixa_vem_vazio_e_loja_desconhecida_404(api_locais):
    corpo = api_locais.get(f"{URL}/pedido-abastecimento", params={"loja": "2"}).json()
    assert (corpo["tem_vendas"], corpo["pedidos"], corpo["sem_estoque"]) == (False, [], [])
    resposta = api_locais.get(f"{URL}/pedido-abastecimento", params={"loja": "77"})
    assert resposta.status_code == 404


def _cadastrar(db, *itens):
    for produto, sub in itens:
        db.add(
            Produto(
                id_produto=produto,
                id_subproduto=sub,
                descricao=f"ITEM {sub}",
                sincronizado_em=AGORA,
            )
        )
    db.flush()


def test_excecao_tira_o_item_da_falta_so_na_empresa(api_locais, cobertura_db):
    _cadastrar(cobertura_db, ("1", "1"), ("2", "2"))
    resposta = api_locais.post(
        f"{URL}/excecoes", json={"empresa": "1", "codigo": "1", "motivo": " Só no depósito "}
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"incluidos": 1}

    assert api_locais.post(f"{URL}/excecoes", json={"empresa": "1", "codigo": "1"}).json() == {
        "incluidos": 0
    }

    [excecao] = api_locais.get(f"{URL}/excecoes", params={"empresa": "1"}).json()
    assert (excecao["id_subproduto"], excecao["descricao"], excecao["motivo"]) == (
        "1",
        "ITEM 1",
        "Só no depósito",
    )
    assert excecao["usuario_nome"]

    corpo = api_locais.get(URL, params={**JANELA, "empresa": "1"}).json()
    itens = {i["id_produto"]: i for i in corpo["itens"]}
    assert (itens["1"]["status_cobertura"], itens["1"]["excecao"]) == (None, True)
    assert itens["2"]["excecao"] is False
    resumo = api_locais.get(f"{URL}/cobertura", params={**JANELA, "empresa": "1"}).json()
    assert resumo["produtos"]["ruptura"] == 0
    lojas = api_locais.get(f"{URL}/cobertura/lojas", params=JANELA).json()
    loja1 = next(e for e in lojas["empresas"] if e["empresa"]["codigo"] == "1")
    assert loja1["excecoes"] == 1
    assert loja1["produtos"]["ruptura"] == 0
    assert loja1["locais"][0]["produtos"]["ruptura"] == 0

    rede = api_locais.get(URL, params={**JANELA, "produto": "1"}).json()
    assert rede["itens"][0]["status_cobertura"] == "adequada"

    assert api_locais.delete(f"{URL}/excecoes/1/1/1").status_code == 204
    assert api_locais.delete(f"{URL}/excecoes/1/1/1").status_code == 404
    resumo = api_locais.get(f"{URL}/cobertura", params={**JANELA, "empresa": "1"}).json()
    assert resumo["produtos"]["ruptura"] == 1


def test_excecao_pela_grade_inclui_os_itens_e_codigo_desconhecido_404(api, cobertura_db):
    _cadastrar(cobertura_db, ("50", "51"), ("50", "52"), ("60", "60"))
    resposta = api.post(f"{URL}/excecoes", json={"empresa": "2", "codigo": "50"})
    assert resposta.json() == {"incluidos": 2}
    assert [x["id_subproduto"] for x in api.get(f"{URL}/excecoes").json()] == ["51", "52"]

    assert api.post(f"{URL}/excecoes", json={"empresa": "1", "codigo": "52"}).json() == {
        "incluidos": 1
    }

    resposta = api.post(f"{URL}/excecoes", json={"empresa": "1", "codigo": "999"})
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Produto 999 não encontrado no cadastro."
    assert api.post(f"{URL}/excecoes", json={"empresa": "77", "codigo": "60"}).status_code == 404


def test_locais_somados_da_configuracao():
    from app.core.config import Settings

    settings = Settings(estoque_locais_somados="1:1=8+9, 2:10=17+10 ,lixo,3:")
    assert settings.locais_somados == {("1", "8"): "1", ("1", "9"): "1", ("2", "17"): "10"}
    assert Settings(estoque_locais_somados="").locais_somados == {}
    assert Settings(estoque_locais_fora_da_loja=" avarias , ,Piso").locais_fora_da_loja == (
        "AVARIAS",
        "PISO",
    )


@pytest.mark.parametrize("rota", ["", "/cobertura", "/exportar"])
def test_local_sem_empresa_422(api, rota):
    resposta = api.get(f"{URL}{rota}", params={"local": "1"})
    assert resposta.status_code == 422
    assert resposta.json()["detail"] == "`local` exige `empresa`."


@pytest.mark.parametrize("dias", [6, 181])
def test_janela_fora_do_limite_422(api, dias):
    assert api.get(URL, params={"janela_dias": dias}).status_code == 422


@pytest.mark.parametrize(
    ("disponivel", "media", "esperado"),
    [
        ("0", "2", (Decimal("0.0"), "ruptura")),
        ("-3", "2", (Decimal("0.0"), "ruptura")),
        ("13", "2", (Decimal("6.5"), "critica")),
        ("14", "2", (Decimal("7.0"), "baixa")),
        ("30", "2", (Decimal("15.0"), "adequada")),
        ("180", "2", (Decimal("90.0"), "adequada")),
        ("181", "2", (Decimal("90.5"), "excesso")),
        ("5", None, (None, "sem_giro")),
        ("0", None, (None, None)),
    ],
)
def test_classificacao_nos_limites(disponivel, media, esperado):
    assert classificar_cobertura(Decimal(disponivel), Decimal(media) if media else None) == esperado
