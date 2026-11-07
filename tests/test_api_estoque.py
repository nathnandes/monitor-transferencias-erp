from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.database.models import Empresa, EstoqueEmpresaLocalLote, Sincronizacao
from app.erp.servicos import SaldoEstoque
from app.sync.estoque import _gravar, recalcular_estoque_consolidado
from tests.conftest import app_com_sessao, token_para
from tests.sync_fakes import fabrica_de

pytestmark = pytest.mark.integration

URL = "/api/v1/estoque"
AGORA = datetime(2026, 10, 7, 18, 0, tzinfo=UTC)


def _saldo(produto, atual, disponivel=None, reservado="0", sub=None, local="1"):
    return SaldoEstoque(
        id_empresa="",
        id_produto=produto,
        id_subproduto=sub or produto,
        id_local_estoque=local,
        descricao_local_estoque=f"LOCAL {local}",
        utiliza_lote=False,
        descricao_lote="",
        permite_estoque_negativo=False,
        saldo_atual=Decimal(atual),
        saldo_reservado=Decimal(reservado),
        saldo_disponivel=Decimal(disponivel if disponivel is not None else atual),
        data_alteracao=AGORA,
        inativo_erp=False,
    )


@pytest.fixture
def estoque_db(db_vazio):
    db = db_vazio
    empresas = {}
    for codigo, ativo in (("1", True), ("2", True), ("10", True), ("9", False)):
        empresa = Empresa(id_erp=codigo, codigo=codigo, nome=f"Loja {codigo}", ativo=ativo)
        db.add(empresa)
        empresas[codigo] = empresa
    execucao = Sincronizacao(tipo="estoque", status="sucesso", inicio=AGORA, fim=AGORA)
    db.add(execucao)
    db.flush()

    dados = {
        "1": [
            _saldo("10", "5", local="1"),
            _saldo("10", "3", local="2"),
            _saldo("2", "7", disponivel="4", reservado="3"),
            _saldo("30", "-4"),
        ],
        "2": [_saldo("10", "2"), _saldo("2", "0")],
        "10": [_saldo("2", "1")],
        "9": [_saldo("10", "1000")],
    }
    for codigo, saldos in dados.items():
        _gravar(db, empresas[codigo].id, execucao.id, saldos, AGORA)

    _gravar(db, empresas["2"].id, execucao.id, [_saldo("10", "99", local="7")], AGORA)
    db.query(EstoqueEmpresaLocalLote).filter_by(id_local_estoque="7").update({"ativo": False})
    db.flush()
    recalcular_estoque_consolidado(
        fabrica_de(db), ambiente="producao", empresas=("1", "2", "10"), agora=lambda: AGORA
    )
    return db


@pytest.fixture
def api_estoque(estoque_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.estoque", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(estoque_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def _produtos(corpo):
    return [(i["id_produto"], i["saldo_atual"]) for i in corpo["itens"]]


@pytest.mark.parametrize("rota", [URL, f"{URL}/resumo", f"{URL}/10/10", f"{URL}/exportar"])
def test_sem_token_401(client, rota):
    assert client.get(rota).status_code == 401


@pytest.mark.parametrize("rota", [URL, f"{URL}/resumo", f"{URL}/10/10", f"{URL}/exportar"])
def test_sem_modulo_estoque_403(db_vazio, criar_usuario_teste, rota):
    operador = criar_usuario_teste("op.sem.estoque", "OPERADOR", modulos=["DASHBOARD"])
    app = app_com_sessao(db_vazio)
    assert TestClient(app, headers=token_para(app, operador)).get(rota).status_code == 403


def test_lista_consolidado_em_ordem_numerica_de_produto(api_estoque):
    corpo = api_estoque.get(URL).json()

    assert _produtos(corpo) == [("2", "8.000"), ("10", "10.000"), ("30", "-4.000")]
    assert corpo["total"] == 3
    assert corpo["atualizado_em"] == "2026-10-07T18:00:00Z"
    item = corpo["itens"][0]
    assert item == {
        "id_produto": "2",
        "id_subproduto": "2",
        "saldo_atual": "8.000",
        "saldo_reservado": "3.000",
        "saldo_disponivel": "5.000",
        "empresas_com_estoque": 2,
        "descricao": None,
        "preco_varejo_min": None,
        "preco_varejo_max": None,
        "custo_gerencial": None,
        "valor_custo": None,
        "fabricante": None,
        "fornecedor": None,
        "excecao": False,
        "venda_media_diaria": None,
        "cobertura_dias": None,
        "status_cobertura": None,
    }


@pytest.mark.parametrize(
    ("situacao", "esperado"),
    [
        ("com_saldo", ["2", "10"]),
        ("negativo", ["30"]),
        ("com_reserva", ["2"]),
        ("sem_saldo", []),
    ],
)
def test_filtro_por_situacao(api_estoque, situacao, esperado):
    corpo = api_estoque.get(URL, params={"situacao": situacao}).json()
    assert [p for p, _ in _produtos(corpo)] == esperado


def test_filtro_por_produto_e_ordenacao_por_saldo(api_estoque):
    assert _produtos(api_estoque.get(URL, params={"produto": "10"}).json()) == [("10", "10.000")]
    maior = api_estoque.get(URL, params={"ordenacao": "maior_saldo"}).json()
    assert [p for p, _ in _produtos(maior)] == ["10", "2", "30"]
    menor = api_estoque.get(URL, params={"ordenacao": "menor_saldo"}).json()
    assert [p for p, _ in _produtos(menor)] == ["30", "2", "10"]


def test_por_empresa_soma_os_locais_so_daquela_empresa(api_estoque):
    corpo = api_estoque.get(URL, params={"empresa": "1"}).json()

    assert _produtos(corpo) == [("2", "7.000"), ("10", "8.000"), ("30", "-4.000")]
    assert [i["empresas_com_estoque"] for i in corpo["itens"]] == [1, 1, 0]
    sem_saldo = api_estoque.get(URL, params={"empresa": "2", "situacao": "sem_saldo"}).json()
    assert _produtos(sem_saldo) == [("2", "0.000")]


def test_empresa_desconhecida_404(api_estoque):
    resposta = api_estoque.get(URL, params={"empresa": "77"})
    assert resposta.status_code == 404
    assert "77" in resposta.json()["detail"]


def test_paginacao(api_estoque):
    corpo = api_estoque.get(URL, params={"tamanho_pagina": 2, "pagina": 2}).json()

    assert (corpo["total"], corpo["total_paginas"], corpo["pagina"]) == (3, 2, 2)
    assert _produtos(corpo) == [("30", "-4.000")]
    assert api_estoque.get(URL, params={"tamanho_pagina": 101}).status_code == 422


def test_resumo(api_estoque):
    corpo = api_estoque.get(f"{URL}/resumo").json()

    assert {k: corpo[k] for k in ("produtos", "produtos_com_saldo", "produtos_negativos")} == {
        "produtos": 3,
        "produtos_com_saldo": 2,
        "produtos_negativos": 1,
    }
    assert corpo["produtos_com_reserva"] == 1
    assert corpo["atualizado_em"] == "2026-10-07T18:00:00Z"
    assert corpo["ultima_sincronizacao"]["status"] == "sucesso"

    assert [
        (e["empresa"]["codigo"], e["produtos_com_saldo"], e["linhas"]) for e in corpo["por_empresa"]
    ] == [("1", 2, 4), ("2", 1, 2), ("10", 1, 1)]


def test_detalhe_por_empresa_e_local(api_estoque):
    corpo = api_estoque.get(f"{URL}/10/10").json()

    assert (corpo["saldo_atual"], corpo["empresas_com_estoque"]) == ("10.000", 2)
    empresas = corpo["empresas"]
    assert [(e["empresa"]["codigo"], e["saldo_atual"]) for e in empresas] == [
        ("1", "8.000"),
        ("2", "2.000"),
    ]
    locais = empresas[0]["locais"]
    assert [(x["id_local_estoque"], x["saldo_atual"]) for x in locais] == [
        ("1", "5.000"),
        ("2", "3.000"),
    ]
    assert locais[0]["descricao_local_estoque"] == "LOCAL 1"
    assert locais[0]["data_alteracao_erp"] == "2026-10-07T18:00:00Z"

    assert all(x["id_local_estoque"] != "7" for e in empresas for x in e["locais"])


def test_produto_sem_estoque_404(api_estoque):
    assert api_estoque.get(f"{URL}/999/999").status_code == 404


@pytest.fixture
def api_precos(estoque_db, criar_usuario_teste):
    from app.database.models import PrecoProdutoEmpresa, Produto

    db = estoque_db
    ids = {e.codigo: e.id for e in db.query(Empresa)}
    db.add(
        Produto(
            id_produto="10", id_subproduto="10", descricao="CAFE FICTICIO", sincronizado_em=AGORA
        )
    )
    for codigo, produto, varejo, custo in (
        ("1", "10", "10", "4"),
        ("2", "10", "12", "5"),
        ("9", "10", "1", "1"),
        ("1", "2", "6", "3"),
    ):
        db.add(
            PrecoProdutoEmpresa(
                empresa_id=ids[codigo],
                id_produto=produto,
                id_subproduto=produto,
                preco_varejo=Decimal(varejo),
                custo_gerencial=Decimal(custo),
                sincronizado_em=AGORA,
            )
        )
    db.flush()
    operador = criar_usuario_teste("op.precos", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def _por_produto(corpo):
    return {i["id_produto"]: i for i in corpo["itens"]}


def test_consolidado_traz_faixa_de_preco_custo_medio_e_valor(api_precos):
    itens = _por_produto(api_precos.get(URL).json())

    cafe = itens["10"]
    assert cafe["descricao"] == "CAFE FICTICIO"
    assert Decimal(cafe["preco_varejo_min"]) == 10 and Decimal(cafe["preco_varejo_max"]) == 12
    assert Decimal(cafe["valor_custo"]) == 42
    assert Decimal(cafe["custo_gerencial"]) == Decimal("4.2")

    assert Decimal(itens["2"]["valor_custo"]) == 21
    assert itens["2"]["descricao"] is None
    assert itens["30"]["valor_custo"] is None and itens["30"]["preco_varejo_min"] is None


def test_por_empresa_usa_preco_e_custo_da_empresa(api_precos):
    itens = _por_produto(api_precos.get(URL, params={"empresa": "2"}).json())

    assert (
        Decimal(itens["10"]["preco_varejo_min"]) == 12 == Decimal(itens["10"]["preco_varejo_max"])
    )
    assert Decimal(itens["10"]["custo_gerencial"]) == 5
    assert Decimal(itens["10"]["valor_custo"]) == 10


def test_resumo_soma_valor_dos_saldos_positivos(api_precos):
    corpo = api_precos.get(f"{URL}/resumo").json()

    por_empresa = {e["empresa"]["codigo"]: e["valor_custo"] for e in corpo["por_empresa"]}

    assert Decimal(por_empresa["1"]) == 53 and Decimal(por_empresa["2"]) == 10
    assert por_empresa["10"] is None
    assert Decimal(corpo["valor_custo"]) == 63
    assert corpo["linhas_sem_custo"] == 1


def test_detalhe_traz_preco_e_valor_por_empresa(api_precos):
    corpo = api_precos.get(f"{URL}/10/10").json()

    assert corpo["descricao"] == "CAFE FICTICIO"
    empresas = {e["empresa"]["codigo"]: e for e in corpo["empresas"]}
    assert Decimal(empresas["1"]["preco"]["preco_varejo"]) == 10
    assert Decimal(empresas["1"]["valor_custo"]) == 32
    assert Decimal(empresas["2"]["preco"]["custo_gerencial"]) == 5


@pytest.fixture
def api_fornecedores(estoque_db, criar_usuario_teste):
    from datetime import date

    from app.database.models import MovimentoEstoque, NotaMovimento, Produto

    db = estoque_db
    ids = {e.codigo: e.id for e in db.query(Empresa)}
    db.add(
        Produto(id_produto="10", id_subproduto="10", marca="MARCA FICTICIA", sincronizado_em=AGORA)
    )
    compras = (
        ("1", "700", date(2026, 9, 1), "10", "50", "11111111000111", "ALFA LTDA"),
        ("2", "701", date(2026, 9, 20), "4", "24", "11111111000111", "ALFA LTDA"),
        ("1", "702", date(2026, 10, 2), "6", "30", "22222222000122", "BETA SA"),
    )
    for codigo, planilha, dia, quantidade, valor, cnpj, nome in compras:
        db.add(
            MovimentoEstoque(
                empresa_id=ids[codigo],
                dia=dia,
                coi=11,
                tipo="compra",
                id_planilha=planilha,
                sequencia="1",
                id_produto="10",
                id_subproduto="10",
                quantidade=Decimal(quantidade),
                valor=Decimal(valor),
                sincronizado_em=AGORA,
            )
        )
        db.add(
            NotaMovimento(
                empresa_id=ids[codigo],
                id_planilha=planilha,
                saida=False,
                encontrado=True,
                cnpj_emitente=cnpj,
                nome_emitente=nome,
                emitente_lido=True,
                sincronizado_em=AGORA,
            )
        )

    db.add(
        MovimentoEstoque(
            empresa_id=ids["2"],
            dia=date(2026, 10, 5),
            coi=85,
            tipo="transferencia_entrada",
            id_planilha="703",
            id_produto="10",
            id_subproduto="10",
            quantidade=Decimal("1"),
            sincronizado_em=AGORA,
        )
    )
    db.add(
        NotaMovimento(
            empresa_id=ids["2"],
            id_planilha="703",
            saida=False,
            encontrado=True,
            nome_emitente="LOJA 1",
            emitente_lido=True,
            sincronizado_em=AGORA,
        )
    )
    db.flush()
    operador = criar_usuario_teste("op.fornecedor", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_lista_traz_fabricante_e_ultimo_fornecedor(api_fornecedores):
    itens = _por_produto(api_fornecedores.get(URL).json())

    assert (itens["10"]["fabricante"], itens["10"]["fornecedor"]) == ("MARCA FICTICIA", "BETA SA")
    assert (itens["2"]["fabricante"], itens["2"]["fornecedor"]) == (None, None)

    linhas = _csv(api_fornecedores.get(f"{URL}/exportar"))
    cafe = next(c for c in linhas[1:] if c[0] == "10")
    assert cafe[3:5] == ["MARCA FICTICIA", "BETA SA"]


def test_filtra_por_qualquer_fornecedor_das_compras_do_item(api_fornecedores):

    for cnpj in ("11111111000111", "22222222000122"):
        corpo = api_fornecedores.get(URL, params={"fornecedor": cnpj}).json()
        assert [i["id_produto"] for i in corpo["itens"]] == ["10"]
        assert corpo["total"] == 1

    assert api_fornecedores.get(URL, params={"fornecedor": "99999999000199"}).json()["total"] == 0

    linhas = _csv(api_fornecedores.get(f"{URL}/exportar", params={"fornecedor": "11111111000111"}))
    assert [c[0] for c in linhas[1:]] == ["10"]


def test_lista_os_fornecedores_em_ordem_de_nome(api_fornecedores):

    assert api_fornecedores.get(f"{URL}/fornecedores").json() == [
        {"cnpj": "11111111000111", "nome": "ALFA LTDA", "itens": 1},
        {"cnpj": "22222222000122", "nome": "BETA SA", "itens": 1},
    ]


def test_detalhe_traz_os_fornecedores_da_compra_mais_recente(api_fornecedores):
    corpo = api_fornecedores.get(f"{URL}/10/10").json()

    assert corpo["fabricante"] == "MARCA FICTICIA"
    assert [
        (
            f["nome"],
            f["cnpj"],
            f["compras"],
            f["quantidade"],
            f["ultima_compra"],
            f["ultima_empresa"]["codigo"],
            f["custo_ultima"],
        )
        for f in corpo["fornecedores"]
    ] == [
        ("BETA SA", "22222222000122", 1, "6.0000", "2026-10-02", "1", "5.0000"),
        ("ALFA LTDA", "11111111000111", 2, "14.0000", "2026-09-20", "2", "6.0000"),
    ]


def _csv(resposta) -> list[list[str]]:
    texto = resposta.content.decode("utf-8")
    assert texto.startswith("﻿")
    return [linha.split(";") for linha in texto.lstrip("﻿").splitlines()]


def test_exportar_usa_os_filtros_da_lista_e_formata_para_o_excel(api_estoque):
    resposta = api_estoque.get(f"{URL}/exportar", params={"empresa": "1", "situacao": "com_saldo"})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert 'filename="estoque_empresa_1_' in resposta.headers["content-disposition"]
    assert resposta.headers["x-total-registros"] == "2"
    linhas = _csv(resposta)
    assert linhas[0][:8] == [
        "Produto",
        "Subproduto",
        "Descrição",
        "Fabricante",
        "Último fornecedor",
        "Saldo atual",
        "Reservado",
        "Disponível",
    ]

    assert [(c[0], c[5], c[6], c[7]) for c in linhas[1:]] == [
        ("2", "7", "3", "4"),
        ("10", "8", "0", "8"),
    ]


def test_exportar_empresa_desconhecida_404(api_estoque):
    assert api_estoque.get(f"{URL}/exportar", params={"empresa": "77"}).status_code == 404


@pytest.fixture
def api_grade(estoque_db, criar_usuario_teste):
    from app.database.models import Produto

    db = estoque_db
    loja = db.query(Empresa).filter_by(codigo="1").one()
    execucao = db.query(Sincronizacao).first()
    _gravar(
        db, loja.id, execucao.id, [_saldo("40", "3", sub="41"), _saldo("40", "5", sub="42")], AGORA
    )
    for sub, resumida in (("41", "LONA AZUL 2X2M"), ("42", "LONA AZUL 3X3M")):
        db.add(
            Produto(
                id_produto="40",
                id_subproduto=sub,
                descricao="LONA AZUL",
                descricao_resumida=resumida,
                sincronizado_em=AGORA,
            )
        )
    db.flush()
    recalcular_estoque_consolidado(
        fabrica_de(db), ambiente="producao", empresas=("1", "2", "10"), agora=lambda: AGORA
    )
    operador = criar_usuario_teste("op.grade", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_variacao_de_grade_tem_descricao_e_busca_pelo_proprio_codigo(api_grade):

    corpo = api_grade.get(URL, params={"produto": "42"}).json()
    assert [(i["id_subproduto"], i["descricao"]) for i in corpo["itens"]] == [
        ("42", "LONA AZUL 3X3M")
    ]

    corpo = api_grade.get(URL, params={"produto": "40"}).json()
    assert [i["id_subproduto"] for i in corpo["itens"]] == ["41", "42"]

    detalhe = api_grade.get(f"{URL}/40/41").json()
    assert detalhe["descricao"] == "LONA AZUL 2X2M"


def test_local_de_perda_fica_fora_do_saldo_e_aparece_como_perda(
    estoque_db, criar_usuario_teste, monkeypatch
):
    from app.database.locais_perda import LocalPerda

    monkeypatch.setattr(
        "app.database.locais_perda.locais_de_perda", lambda: (LocalPerda("1", "2", "Avaria"),)
    )
    recalcular_estoque_consolidado(
        fabrica_de(estoque_db), ambiente="producao", empresas=("1", "2", "10"), agora=lambda: AGORA
    )
    operador = criar_usuario_teste("op.perda", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(estoque_db)
    api = TestClient(app, headers=token_para(app, operador))

    assert dict(_produtos(api.get(URL).json()))["10"] == "7.000"
    assert dict(_produtos(api.get(URL, params={"empresa": "1"}).json()))["10"] == "5.000"

    detalhe = api.get(f"{URL}/10/10").json()
    loja1 = next(e for e in detalhe["empresas"] if e["empresa"]["codigo"] == "1")
    assert loja1["saldo_atual"] == "5.000"
    assert {x["id_local_estoque"]: x["perda"] for x in loja1["locais"]} == {
        "1": None,
        "2": "Avaria",
    }
    [local] = api.get(f"{URL}/resumo").json()["locais_perda"]
    assert (local["empresa"]["codigo"], local["id_local"], local["motivo"]) == (
        "1",
        "2",
        "Avaria",
    )
    assert local["produtos"] == 1
    app.dependency_overrides.clear()


def test_configuracao_dos_locais_de_perda():
    from app.core.config import Settings

    settings = Settings(estoque_locais_perda="6:40=Avaria, 1:8 ,lixo,6:40=Repetido")
    assert settings.locais_perda == (("6", "40", "Repetido"), ("1", "8", "Perda"))


def test_lista_monta_a_consulta_pesada_uma_vez_so(estoque_db):
    from sqlalchemy import event

    from app.services.estoque import FiltrosEstoque, listar_estoque

    pesadas: list[str] = []

    def guardar(_conn, _cursor, sql, _params, _contexto, _executemany):
        if "AS saldos" in sql:
            pesadas.append(sql)

    conexao = estoque_db.connection()
    event.listen(conexao, "before_cursor_execute", guardar)
    try:
        pagina = listar_estoque(estoque_db, FiltrosEstoque(), pagina=1, tamanho_pagina=2)
        alem = listar_estoque(estoque_db, FiltrosEstoque(), pagina=99, tamanho_pagina=2)
    finally:
        event.remove(conexao, "before_cursor_execute", guardar)

    assert pagina.total > 2 and len(pagina.itens) == 2
    assert len(pesadas) == 3
    assert (alem.total, alem.itens) == (pagina.total, [])
