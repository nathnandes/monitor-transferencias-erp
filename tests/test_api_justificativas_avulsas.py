from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.database.models import Empresa, Produto
from app.erp.servicos import ItemNota
from app.sync.movimentos import _gravar_dia
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

URL = "/api/v1/estoque/avulsas"
AGORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
HOJE = datetime.now(ZoneInfo(get_settings().tz)).date()
CORTE = HOJE - timedelta(days=3)
PERIODO = {"data_inicial": (HOJE - timedelta(days=10)).isoformat(), "data_final": HOJE.isoformat()}


def _item(coi: int, planilha: str, produto: str, qtd: str, valor: str, seq: str = "1") -> ItemNota:
    return ItemNota(
        id_empresa="",
        id_planilha=planilha,
        id_operacao=coi,
        id_produto=produto,
        id_subproduto=produto,
        sequencia=seq,
        quantidade=Decimal(qtd),
        descricao_produto="BROCHA 3 POL" if coi == 8080 else None,
        data_movimento=AGORA,
        valor_liquido=Decimal(valor),
    )


@pytest.fixture
def api(db_vazio, criar_usuario_teste):
    db = db_vazio
    loja = Empresa(id_erp="1", codigo="1", nome="Loja 1")
    db.add(loja)
    db.add(
        Produto(id_produto="10", id_subproduto="10", descricao="TINTA 18L", sincronizado_em=AGORA)
    )
    db.flush()

    def gravar(dia, *itens):
        _gravar_dia(
            db,
            loja.id,
            dia,
            [(i.id_operacao != 80, i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )

    gravar(HOJE - timedelta(days=5), _item(80, "A1", "10", "2", "200"))
    gravar(HOJE - timedelta(days=1), _item(80, "A2", "10", "1", "100"))
    gravar(
        HOJE,
        _item(8080, "S1", "20", "3", "30", "2"),
        _item(8080, "S1", "21", "1", "5", "10"),
        _item(2000, "B1", "10", "-1", "-100"),
    )
    db.flush()
    operador = criar_usuario_teste("op.avulsas", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    app.state.settings = app.state.settings.model_copy(update={"justificar_avulsas_desde": CORTE})
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def _documentos(api, **params):
    resposta = api.get(f"{URL}/documentos", params={**PERIODO, **params})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_pendentes_sao_as_avulsas_sem_justificativa_desde_o_corte(api):
    corpo = _documentos(api)

    assert corpo["justificar_desde"] == CORTE.isoformat()
    assert [d["id_planilha"] for d in corpo["documentos"]] == ["S1", "A2"]
    s1 = corpo["documentos"][0]
    assert (s1["tipo"], s1["itens"], s1["id_produto"], s1["descricao"]) == (
        "saida_avulsa",
        2,
        "20",
        "BROCHA 3 POL",
    )
    assert Decimal(s1["valor"]) == Decimal("-35")
    assert corpo["documentos"][1]["descricao"] == "TINTA 18L"
    assert corpo["pendentes"] == {"documentos": 2, "valor": "135.00"}
    assert corpo["pendentes_desde_o_corte"]["documentos"] == 2

    todas = _documentos(api, situacao="todas")
    assert [(d["id_planilha"], d["exige_justificativa"]) for d in todas["documentos"]] == [
        ("S1", True),
        ("A2", True),
        ("A1", False),
    ]
    motivos = {m["codigo"]: m for m in corpo["motivos"]}
    assert motivos["uso_consumo"]["tipos"] == ["saida_avulsa"]
    assert motivos["outro"]["exige_observacao"] is True


def test_justificar_tira_das_pendentes_e_registra_quem(api):
    resposta = api.put(
        f"{URL}/1/S1/justificativa",
        json={"motivo": "uso_consumo", "observacao": "  pintura da fachada  "},
    )
    assert resposta.status_code == 200, resposta.text
    j = resposta.json()
    assert (j["motivo_rotulo"], j["observacao"], j["usuario_nome"]) == (
        "Uso e consumo",
        "pintura da fachada",
        "Op.Avulsas",
    )

    pendentes = _documentos(api)
    assert [d["id_planilha"] for d in pendentes["documentos"]] == ["A2"]
    justificadas = _documentos(api, situacao="justificada")
    assert justificadas["documentos"][0]["justificativa"]["motivo"] == "uso_consumo"
    assert justificadas["justificadas"] == 1

    api.put(f"{URL}/1/S1/justificativa", json={"motivo": "avaria", "observacao": None})
    editada = _documentos(api, situacao="justificada")["documentos"][0]["justificativa"]
    assert (editada["motivo"], editada["observacao"]) == ("avaria", None)


def test_motivo_tem_que_valer_para_o_tipo_e_outro_pede_texto(api):
    errado = api.put(f"{URL}/1/A2/justificativa", json={"motivo": "uso_consumo"})
    assert errado.status_code == 422
    assert "entrada avulsa" in errado.json()["detail"]

    sem_texto = api.put(f"{URL}/1/A2/justificativa", json={"motivo": "outro", "observacao": " "})
    assert sem_texto.status_code == 422

    ok = api.put(f"{URL}/1/A2/justificativa", json={"motivo": "mercadoria_encontrada"})
    assert ok.status_code == 200


def test_documento_que_nao_e_avulso_da_404(api):
    assert (
        api.put(
            f"{URL}/1/B1/justificativa", json={"motivo": "outro", "observacao": "x"}
        ).status_code
        == 404
    )
    assert api.put(f"{URL}/1/NAOEXISTE/justificativa", json={"motivo": "avaria"}).status_code == 404


def test_sem_dia_de_corte_toda_avulsa_sem_justificativa_e_pendente(api):
    api.app.state.settings = api.app.state.settings.model_copy(
        update={"justificar_avulsas_desde": None}
    )
    corpo = _documentos(api)

    assert corpo["justificar_desde"] is None
    assert [(d["id_planilha"], d["exige_justificativa"]) for d in corpo["documentos"]] == [
        ("S1", True),
        ("A2", True),
        ("A1", True),
    ]
    assert corpo["pendentes"]["documentos"] == 3
    assert corpo["pendentes_desde_o_corte"]["documentos"] == 3


def test_justificar_varios_de_uma_vez(api):
    def lote(motivo, *planilhas, observacao=None):
        return api.put(
            f"{URL}/justificativas",
            json={
                "motivo": motivo,
                "observacao": observacao,
                "documentos": [{"empresa": "1", "id_planilha": p} for p in planilhas],
            },
        )

    errado = lote("uso_consumo", "S1", "A2")
    assert errado.status_code == 422
    assert "A2" in errado.json()["detail"]
    assert lote("avaria", "S1", "B1").status_code == 404
    assert _documentos(api, situacao="justificada")["justificadas"] == 0

    ok = lote("outro", "S1", "A2", "A1", "A2", observacao=" acerto do mes ")
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"justificados": 3}
    feitas = _documentos(api, situacao="justificada")["documentos"]
    assert sorted(d["id_planilha"] for d in feitas) == ["A1", "A2", "S1"]
    assert {d["justificativa"]["observacao"] for d in feitas} == {"acerto do mes"}


@pytest.fixture
def api_vinculos(db_vazio, criar_usuario_teste):
    db = db_vazio
    loja1 = Empresa(id_erp="1", codigo="1", nome="Loja 1")
    loja2 = Empresa(id_erp="2", codigo="2", nome="Loja 2")
    db.add_all([loja1, loja2])
    db.flush()

    def gravar(loja, dia, *itens):
        _gravar_dia(
            db,
            loja.id,
            dia,
            [(i.id_operacao != 80, i) for i in itens],
            completo=True,
            execucao_id=None,
            momento=AGORA,
        )

    gravar(loja1, HOJE - timedelta(days=120), _item(8041, "U0", "40", "1", "10"))
    gravar(loja1, HOJE - timedelta(days=6), _item(8041, "U1", "10", "2", "200"))
    gravar(loja1, HOJE - timedelta(days=4), _item(2000, "B0", "10", "-3", "-300"))
    gravar(loja1, HOJE - timedelta(days=3), _item(2000, "B1", "10", "1", "100"))
    gravar(loja1, HOJE - timedelta(days=2), _item(8080, "S1", "10", "2", "200"))
    gravar(
        loja1,
        HOJE - timedelta(days=1),
        _item(8080, "S2", "10", "5", "500"),
        _item(8080, "S2", "30", "1", "10", "2"),
        _item(2000, "B2", "10", "-2", "-200"),
    )
    gravar(loja1, HOJE, _item(80, "E1", "10", "2", "200"), _item(80, "E2", "40", "1", "10", "2"))
    gravar(loja2, HOJE, _item(8080, "X1", "10", "2", "200"))
    db.flush()
    operador = criar_usuario_teste("op.vinculos", "OPERADOR", modulos=["ESTOQUE"])
    app = app_com_sessao(db)
    app.state.settings = app.state.settings.model_copy(update={"justificar_avulsas_desde": CORTE})
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def _doc(api, id_planilha, situacao="todas"):
    corpo = _documentos(api, situacao=situacao)
    return next((d for d in corpo["documentos"] if d["id_planilha"] == id_planilha), None)


def test_entrada_avisa_quando_o_ultimo_balanco_tirou_o_produto(api_vinculos):
    e1 = _doc(api_vinculos, "E1")

    alerta = next(a for a in e1["alertas"] if a["regra"] == "balanco")
    assert (alerta["id_planilha"], alerta["id_produto"], Decimal(alerta["quantidade"])) == (
        "B2",
        "10",
        Decimal(-2),
    )
    assert alerta["dia"] == (HOJE - timedelta(days=1)).isoformat()

    assert _doc(api_vinculos, "E2")["alertas"] == []
    assert _doc(api_vinculos, "S1")["alertas"] == []


def test_entrada_avisa_quando_o_produto_saiu_para_uso_e_consumo(api_vinculos):
    corpo = _documentos(api_vinculos, situacao="todas")
    assert [r["codigo"] for r in corpo["regras"]] == ["balanco", "uso_consumo"]

    e1 = _doc(api_vinculos, "E1")
    alerta = next(a for a in e1["alertas"] if a["regra"] == "uso_consumo")
    assert (alerta["id_planilha"], alerta["id_produto"], Decimal(alerta["quantidade"])) == (
        "U1",
        "10",
        Decimal(-2),
    )
    assert alerta["dia"] == (HOJE - timedelta(days=6)).isoformat()

    filtradas = _documentos(api_vinculos, situacao="todas", alerta="uso_consumo")
    assert [d["id_planilha"] for d in filtradas["documentos"]] == ["E1"]
    assert filtradas["total"] == 1
    assert (
        api_vinculos.get(
            f"{URL}/documentos", params={**PERIODO, "alerta": "nao_existe"}
        ).status_code
        == 422
    )


def test_candidatos_sao_da_mesma_loja_com_o_exato_primeiro(api_vinculos):
    resposta = api_vinculos.get(f"{URL}/1/E1/candidatos")
    assert resposta.status_code == 200, resposta.text
    lista = resposta.json()

    assert [(c["id_planilha"], c["exato"], c["em_comum"]) for c in lista] == [
        ("S1", True, 1),
        ("S2", False, 1),
    ]
    assert lista[0]["tipo"] == "saida_avulsa"
    assert api_vinculos.get(f"{URL}/1/B2/candidatos").status_code == 404


def test_relacionar_justifica_os_dois_e_desfazer_apaga_so_o_que_criou(api_vinculos):

    api_vinculos.put(f"{URL}/1/S2/justificativa", json={"motivo": "avaria"})

    resposta = api_vinculos.put(f"{URL}/1/E1/vinculo", json={"id_planilha": "S1"})
    assert resposta.status_code == 200, resposta.text
    assert (resposta.json()["id_planilha"], resposta.json()["tipo"]) == ("S1", "saida_avulsa")

    e1, s1 = _doc(api_vinculos, "E1"), _doc(api_vinculos, "S1")
    assert (e1["vinculo"]["id_planilha"], s1["vinculo"]["id_planilha"]) == ("S1", "E1")
    assert e1["justificativa"]["motivo"] == "correcao_lancamento"
    assert e1["justificativa"]["pelo_vinculo"] is True
    assert "saída avulsa S1" in e1["justificativa"]["observacao"]
    assert "entrada avulsa E1" in s1["justificativa"]["observacao"]

    assert [c["id_planilha"] for c in api_vinculos.get(f"{URL}/1/S2/candidatos").json()] == []
    conflito = api_vinculos.put(f"{URL}/1/S2/vinculo", json={"id_planilha": "E1"})
    assert conflito.status_code == 409

    api_vinculos.put(f"{URL}/1/S1/justificativa", json={"motivo": "uso_consumo"})
    assert api_vinculos.delete(f"{URL}/1/S1/vinculo").status_code == 204
    assert _doc(api_vinculos, "E1")["vinculo"] is None
    assert _doc(api_vinculos, "E1")["justificativa"] is None
    assert _doc(api_vinculos, "S1")["justificativa"]["motivo"] == "uso_consumo"
    assert api_vinculos.delete(f"{URL}/1/S1/vinculo").status_code == 404


def test_vinculo_so_entre_entrada_e_saida_da_mesma_loja(api_vinculos):
    mesmo_tipo = api_vinculos.put(f"{URL}/1/S1/vinculo", json={"id_planilha": "S2"})
    assert mesmo_tipo.status_code == 422
    outra_loja = api_vinculos.put(f"{URL}/1/E1/vinculo", json={"id_planilha": "X1"})
    assert outra_loja.status_code == 404
    balanco = api_vinculos.put(f"{URL}/1/E1/vinculo", json={"id_planilha": "B2"})
    assert balanco.status_code == 404


def test_admin_muda_o_dia_de_corte_na_tela_e_vale_na_hora(api, db_vazio, criar_usuario_teste):

    assert api.get(f"{URL}/corte").json() == {
        "justificar_desde": CORTE.isoformat(),
        "definido_por": None,
        "atualizado_em": None,
    }

    assert api.put(f"{URL}/corte", json={"justificar_desde": None}).status_code == 403

    admin = criar_usuario_teste("admin.corte", "ADMIN", modulos=["ESTOQUE"])
    como_admin = token_para(api.app, admin)
    resposta = api.put(f"{URL}/corte", json={"justificar_desde": None}, headers=como_admin)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["definido_por"] == "Admin.Corte"

    corpo = _documentos(api)
    assert corpo["justificar_desde"] is None
    assert corpo["corte"]["definido_por"] == "Admin.Corte"
    assert corpo["pendentes"]["documentos"] == 3

    dia = HOJE.isoformat()
    api.put(f"{URL}/corte", json={"justificar_desde": dia}, headers=como_admin)
    assert [d["id_planilha"] for d in _documentos(api)["documentos"]] == ["S1"]
