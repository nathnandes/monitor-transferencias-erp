from datetime import UTC, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.models import Empresa, NotaMovimento
from app.dominio.empresa_errada import eh_empresa_errada
from app.rules.regras import nota_empresa_errada
from app.sync.movimentos import _gravar_dia
from tests.conftest import app_com_sessao, token_para
from tests.test_api_livro_estoque import (
    AGORA,
    HOJE,
    ONTEM,
    URL,
    _item,
    _lado,
    livro_db,  # noqa: F401 (fixture)
)

pytestmark = pytest.mark.integration

CNPJ_1 = "11111111000101"
CNPJ_2 = "11111111000202"


@pytest.fixture
def errada_db(livro_db):  # noqa: F811
    db = livro_db
    empresas = {e.codigo: e for e in db.scalars(select(Empresa))}
    empresas["1"].cnpj, empresas["2"].cnpj = CNPJ_1, CNPJ_2
    antiga = HOJE - timedelta(days=45)

    for dia, itens in (
        (HOJE - timedelta(days=3), [_item(8038, "E1", "5", "45.55"), _item(8038, "E2", "1", "9")]),
        (antiga, [_item(8041, "E3", "2", "20")]),
    ):
        _gravar_dia(
            db,
            empresas["1"].id,
            dia,
            [(_lado(i.id_operacao), i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )
    cabecalhos = (
        ("E1", CNPJ_2, False),
        ("E2", CNPJ_2, True),
        ("E3", CNPJ_2, False),
        ("T1", CNPJ_2, False),
        ("V1", "99999999000199", False),
        ("V2", CNPJ_1, False),
    )
    for planilha, cnpj, cancelada in cabecalhos:
        nota = db.get(NotaMovimento, (empresas["1"].id, planilha))
        if nota is None:
            nota = NotaMovimento(
                empresa_id=empresas["1"].id,
                id_planilha=planilha,
                saida=True,
                encontrado=True,
                numero=f"N{planilha}",
                momento=datetime.combine(ONTEM, time(13, 28), UTC),
                usuario="BEATRIZ",
                sincronizado_em=AGORA,
            )
            db.add(nota)
        nota.cnpj_destinatario = cnpj
        nota.nome_destinatario = f"DESTINO {planilha}"
        nota.cancelada = cancelada
        nota.destinatario_lido = True
    db.flush()
    return db


@pytest.fixture
def api(errada_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.errada", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(errada_db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("destino_id", "cancelada", "categoria", "esperado"),
    [
        (2, False, "uso_consumo", True),
        (2, None, "venda", True),
        (2, True, "uso_consumo", False),
        (2, False, "transferencia_saida", False),
        (1, False, "uso_consumo", False),
        (None, False, "uso_consumo", False),
    ],
)
def test_regra_pura(destino_id, cancelada, categoria, esperado):
    assert (
        eh_empresa_errada(
            empresa_id=1, destino_id=destino_id, cancelada=cancelada, categoria=categoria
        )
        is esperado
    )


def test_livro_marca_e_filtra_as_notas_da_empresa_errada(api):
    params = {"data_inicial": str(HOJE - timedelta(days=60)), "data_final": str(HOJE)}
    todas = api.get(f"{URL}/livro/notas", params=params).json()["notas"]
    marcadas = {x["id_planilha"] for x in todas if x["empresa_errada"]}

    corpo = api.get(f"{URL}/livro/notas", params={**params, "empresa_errada": True}).json()

    assert marcadas == {"E1", "E3"}
    assert corpo["total"] == 2
    assert [x["id_planilha"] for x in corpo["notas"]] == ["E1", "E3"]
    e1 = corpo["notas"][0]
    assert (e1["destinatario"], e1["destino_empresa"], e1["coi"]) == ("DESTINO E1", "2", 8038)

    t1 = next(x for x in todas if x["id_planilha"] == "T1")
    assert (t1["destino_empresa"], t1["empresa_errada"]) == ("2", False)


def test_alerta_para_cada_nota_errada_nao_cancelada(errada_db):
    ocorrencias = nota_empresa_errada(errada_db, datetime.combine(HOJE, time(12), UTC))

    assert [o.detalhes["id_planilha"] for o in ocorrencias] == ["E1", "E3"]
    o = ocorrencias[0]
    assert o.severidade == "CRITICAL"
    assert o.titulo == "NF NE1 emitida na empresa 1 para a empresa 2"
    campos = o.detalhes["campos"]
    assert (campos["origem"], campos["destino"], campos["valor"]) == (
        "1 - Loja 1",
        "2 - Loja 2",
        "R$ 45,55",
    )
    assert campos["coi"] == "8038 - OPERACAO 8038"
    assert "cancele a nota e emita de novo na empresa 2" in campos["orientacao"]
    assert sorted(o.detalhes["empresas_ids"]) == sorted(
        e.id for e in errada_db.scalars(select(Empresa))
    )
