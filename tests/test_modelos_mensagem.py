from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.database.models import Alerta, AlertaConfiguracao, AlertaDestino, ModeloMensagem
from app.notifications.mensagens import montar_texto
from app.notifications.modelos import (
    MODELOS,
    PADRAO_AVISO,
    ModeloInvalido,
    previa,
    renderizar,
    validar,
)
from app.notifications.outbox import processar_pendentes
from app.notifications.resumo_diario import montar_resumo
from app.rules.catalogo import CATALOGO
from app.rules.motor import avaliar
from tests.conftest import app_com_sessao, token_para

TZ = ZoneInfo("America/Porto_Velho")
AGORA = datetime(2026, 10, 2, 9, 0, tzinfo=TZ)
URL = "/api/v1/admin/alertas"
SETTINGS = get_settings().model_copy(update={"tz": "America/Porto_Velho"})


class EnviadorFalso:
    canal = "telegram"

    def __init__(self) -> None:
        self.envios: list[str] = []

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        self.envios.append(texto)


def test_renderiza_variaveis_e_junta_linhas_em_branco():
    texto = renderizar("{a}\n\n{vazio}\n\n{b} · {c}", {"a": "A", "vazio": "", "b": "B", "c": ""})
    assert texto == "A\n\nB ·"


def test_cada_regra_tem_modelo_de_aviso_e_de_resolucao():
    for regra, definicao in CATALOGO.items():
        assert f"{regra}:aviso" in MODELOS

        assert (f"{regra}:resolucao" in MODELOS) == (definicao.tipo == "alerta")
    assert "resumo_diario" in MODELOS


def test_padrao_e_a_mensagem_de_antes_dos_modelos():
    alerta = Alerta(
        id=7,
        regra="transferencia_erro",
        severidade="CRITICAL",
        titulo="Transferência X",
        mensagem="Origem: 01",
        detalhes={},
        aberto_em=AGORA,
    )
    assert montar_texto(alerta, "ABERTURA", TZ) == (
        "🚨 CRITICAL: Transferência X\n\nOrigem: 01\n\nDesde 02/10 09:00 · alerta #7"
    )


def test_modelo_personalizado_usa_os_campos_do_alerta():
    alerta = Alerta(
        id=7,
        regra="transferencia_erro",
        severidade="ERROR",
        titulo="Transferência X",
        mensagem="antiga",
        detalhes={"campos": {"nota": "NF 9", "origem": "1 - Matriz"}},
        aberto_em=AGORA,
    )
    texto = montar_texto(alerta, "ESCALADA", TZ, None, "{agravou}{nivel} · {nota} de {origem}")
    assert texto == "AGRAVOU PARA erro · NF 9 de 1 - Matriz"


@pytest.mark.parametrize(
    ("texto", "trecho"),
    [
        ("   ", "não pode ficar vazio"),
        ("{nota} {inexistente}", "{inexistente}"),
        ("x" * 3001, "3000 caracteres"),
    ],
)
def test_valida_o_modelo(texto, trecho):
    with pytest.raises(ModeloInvalido, match=trecho.replace("{", r"\{").replace("}", r"\}")):
        validar(MODELOS["transferencia_erro:aviso"], texto)


def test_previa_usa_os_exemplos():
    texto = previa(MODELOS["transferencia_atrasada:aviso"], "{nota}: {sem_entrada_ha}")
    assert texto == "NF 123456: 26h"


integration = pytest.mark.integration


@pytest.fixture
def cfg_db(api_db):
    api_db.execute(delete(AlertaConfiguracao))
    api_db.execute(delete(AlertaDestino))
    api_db.execute(delete(ModeloMensagem))
    api_db.add(AlertaDestino(nome="Padrão", chat_id=None))
    api_db.flush()
    return api_db


@pytest.fixture
def admin_api(cfg_db, criar_usuario_teste):
    admin = criar_usuario_teste("admin.modelos", "ADMIN", modulos=["ADMINISTRACAO"])
    app = app_com_sessao(cfg_db)
    yield TestClient(app, headers=token_para(app, admin))
    app.dependency_overrides.clear()


def _modelo(corpo: dict, chave: str) -> dict:
    return next(m for m in corpo["modelos"] if m["chave"] == chave)


@integration
def test_api_lista_os_modelos_no_padrao(admin_api):
    corpo = admin_api.get(URL).json()
    assert {m["chave"] for m in corpo["modelos"]} == set(MODELOS)
    aviso = _modelo(corpo, "transferencia_coi_errado:aviso")
    assert aviso["texto"] == aviso["padrao"] == PADRAO_AVISO
    assert not aviso["personalizado"] and aviso["atualizado_por"] is None
    assert {"nota", "problemas", "emoji", "campos"} <= {v["chave"] for v in aviso["variaveis"]}


@integration
def test_api_salva_e_volta_ao_padrao(admin_api):
    chave = "transferencia_erro:aviso"
    resposta = admin_api.put(f"{URL}/modelos/{chave}", json={"texto": "  ❌ {nota}: {status}  "})
    assert resposta.status_code == 200
    modelo = _modelo(resposta.json(), chave)
    assert modelo["texto"] == "❌ {nota}: {status}"
    assert modelo["personalizado"] and modelo["atualizado_por"]

    restaurado = admin_api.delete(f"{URL}/modelos/{chave}").json()
    assert not _modelo(restaurado, chave)["personalizado"]


@integration
def test_api_salvar_o_padrao_nao_personaliza(admin_api):
    chave = "transferencia_erro:aviso"
    corpo = admin_api.put(f"{URL}/modelos/{chave}", json={"texto": PADRAO_AVISO}).json()
    assert not _modelo(corpo, chave)["personalizado"]


@integration
def test_api_previa_e_erros(admin_api):
    previa_ok = admin_api.post(
        f"{URL}/modelos/resumo_diario/previa", json={"texto": "Bom dia! {data}"}
    )
    assert previa_ok.json() == {"texto": "Bom dia! 31/10/2026"}

    invalida = admin_api.put(f"{URL}/modelos/resumo_diario", json={"texto": "{nota}"})
    assert invalida.status_code == 422
    assert "{nota}" in invalida.json()["detail"]
    assert admin_api.put(f"{URL}/modelos/nao_existe", json={"texto": "x"}).status_code == 404


@integration
def test_api_exige_admin(cfg_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.modelos", "OPERADOR", modulos=["ALERTAS"])
    app = app_com_sessao(cfg_db)
    cliente = TestClient(app, headers=token_para(app, operador))
    assert cliente.put(f"{URL}/modelos/resumo_diario", json={"texto": "x"}).status_code == 403
    app.dependency_overrides.clear()


@integration
def test_outbox_envia_com_o_modelo_personalizado(cfg_db):
    cfg_db.add(
        ModeloMensagem(
            chave="transferencia_erro:aviso", texto="ERRO NA {nota}", usuario_nome="Admin"
        )
    )
    cfg_db.flush()
    agora = cfg_db.scalar(select(func.now()))
    avaliar(cfg_db, agora)
    enviador = EnviadorFalso()

    processar_pendentes(cfg_db, enviador, agora, TZ, lote=500)

    erros = [t for t in enviador.envios if t.startswith("ERRO NA ")]
    assert erros, "o seed tem transferencias com erro"

    assert any(t.startswith("🚨 CRITICAL:") for t in enviador.envios)


@integration
def test_resumo_diario_com_o_modelo_personalizado(cfg_db):
    agora = cfg_db.scalar(select(func.now()))
    padrao = montar_resumo(cfg_db, agora, SETTINGS)
    assert padrao.startswith("☀️ Resumo de ") and "Transferências\n• emitidas ontem:" in padrao

    cfg_db.add(
        ModeloMensagem(
            chave="resumo_diario", texto="{data}: {coi_errado} com COI errado", usuario_nome="A"
        )
    )
    cfg_db.flush()
    texto = montar_resumo(cfg_db, agora, SETTINGS)
    assert texto.endswith("com COI errado") and "\n" not in texto
