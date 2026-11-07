from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.database.models import (
    Alerta,
    AlertaConfiguracao,
    AlertaDestino,
    Empresa,
    Notificacao,
    Transferencia,
)
from app.notifications.mensagens import montar_texto
from app.notifications.outbox import processar_pendentes
from app.rules.catalogo import CATALOGO, montar_corpo
from app.rules.motor import avaliar
from app.services import config_alertas as service
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

TZ = ZoneInfo("America/Porto_Velho")
URL = "/api/v1/admin/alertas"


class EnviadorFalso:
    canal = "telegram"

    def __init__(self) -> None:
        self.envios: list[tuple[str | None, str]] = []

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        self.envios.append((chat_id, texto))


@pytest.fixture
def cfg_db(api_db):
    api_db.execute(delete(AlertaConfiguracao))
    api_db.execute(delete(AlertaDestino))
    api_db.add(AlertaDestino(nome="Padrão", chat_id=None))
    api_db.flush()
    return api_db


def _agora(db):
    return db.scalar(select(func.now()))


def _padrao(db) -> AlertaDestino:
    return db.scalar(select(AlertaDestino).where(AlertaDestino.chat_id.is_(None)))


def _destino(db, nome: str, chat: str, **kw) -> AlertaDestino:
    d = AlertaDestino(nome=nome, chat_id=chat, **kw)
    db.add(d)
    db.flush()
    return d


def _salvar(db, regra: str, **kw) -> None:
    definicao = CATALOGO[regra]
    service.salvar_regra(
        db,
        regra,
        ativo=kw.get("ativo", True),
        campos=kw.get("campos", definicao.campos_padrao),
        destinos_ids=[d.id for d in kw.get("destinos", [])],
    )


def _notificacoes(db, regra: str) -> list[Notificacao]:
    return list(
        db.scalars(
            select(Notificacao).join(Alerta).where(Alerta.regra == regra).order_by(Notificacao.id)
        )
    )


def test_sem_configuracao_tudo_vai_para_o_destino_padrao(cfg_db):
    avaliar(cfg_db, _agora(cfg_db))
    padrao = _padrao(cfg_db)
    destinos = {n.destino_id for n in cfg_db.scalars(select(Notificacao))}
    assert destinos == {padrao.id}


def test_regra_vai_so_para_os_destinos_escolhidos(cfg_db):
    grupo = _destino(cfg_db, "Grupo COI", "-8001")
    _salvar(cfg_db, "transferencia_coi_errado", destinos=[grupo])

    avaliar(cfg_db, _agora(cfg_db))

    assert {n.destino_id for n in _notificacoes(cfg_db, "transferencia_coi_errado")} == {grupo.id}

    assert {n.destino_id for n in _notificacoes(cfg_db, "transferencia_erro")} == {
        _padrao(cfg_db).id
    }


def test_regra_sem_destino_abre_alerta_mas_nao_notifica(cfg_db):
    _salvar(cfg_db, "transferencia_erro", destinos=[])
    avaliar(cfg_db, _agora(cfg_db))
    assert cfg_db.scalar(
        select(func.count()).select_from(Alerta).where(Alerta.regra == "transferencia_erro")
    )
    assert _notificacoes(cfg_db, "transferencia_erro") == []


def test_destino_com_severidade_minima_so_recebe_critico(cfg_db):
    gerente = _destino(cfg_db, "Gerente", "111", severidade_minima="CRITICAL")
    _salvar(cfg_db, "transferencia_atrasada", destinos=[gerente])

    avaliar(cfg_db, _agora(cfg_db))

    severidades = {n.alerta.severidade for n in _notificacoes(cfg_db, "transferencia_atrasada")}
    assert severidades == {"CRITICAL"}
    avisos = cfg_db.scalars(
        select(Alerta).where(
            Alerta.regra == "transferencia_atrasada", Alerta.severidade == "WARNING"
        )
    ).all()
    assert avisos and all(a.notificacoes == [] for a in avisos)


def test_destino_com_empresas_so_recebe_alertas_delas(cfg_db):
    transferencia = (
        cfg_db.scalars(
            select(Transferencia).join(Alerta, Alerta.transferencia_id == Transferencia.id)
        ).first()
        or cfg_db.scalars(select(Transferencia).where(Transferencia.problemas_coi != [])).first()
    )
    assert transferencia is not None
    empresa = transferencia.empresa_origem_id
    loja = _destino(cfg_db, "Grupo da loja", "222", empresas=[empresa])
    for regra in ("transferencia_erro", "transferencia_atrasada", "transferencia_coi_errado"):
        _salvar(cfg_db, regra, destinos=[loja])

    avaliar(cfg_db, _agora(cfg_db))

    notificacoes = list(
        cfg_db.scalars(select(Notificacao).where(Notificacao.destino_id == loja.id))
    )
    assert notificacoes
    for n in notificacoes:
        assert empresa in n.alerta.detalhes["empresas_ids"]


def test_alerta_sem_empresa_vai_para_destino_filtrado():
    from app.rules.config import ConfigRegra, Configuracao

    loja = AlertaDestino(
        nome="Loja", chat_id="1", ativo=True, severidade_minima="WARNING", empresas=[9]
    )
    config = Configuracao({"r": ConfigRegra("r", True, [], [loja])}, [])
    assert config.destinos_para("r", "WARNING", []) == [loja]
    assert config.destinos_para("r", "WARNING", [5]) == []
    assert config.destinos_para("r", "WARNING", [5, 9]) == [loja]


def test_destino_desligado_nao_recebe(cfg_db):
    padrao = _padrao(cfg_db)
    padrao.ativo = False
    cfg_db.flush()
    avaliar(cfg_db, _agora(cfg_db))
    assert cfg_db.scalar(select(func.count()).select_from(Notificacao)) == 0


def test_resolucao_so_vai_para_quem_recebeu_a_abertura(cfg_db):
    gerente = _destino(cfg_db, "Gerente", "111", severidade_minima="CRITICAL")
    _salvar(cfg_db, "transferencia_erro", destinos=[_padrao(cfg_db), gerente])
    agora = _agora(cfg_db)
    avaliar(cfg_db, agora)
    alerta = cfg_db.scalars(select(Alerta).where(Alerta.regra == "transferencia_erro")).first()
    assert alerta is not None
    cfg_db.get(Transferencia, alerta.transferencia_id).status = "PROCESSADA"
    cfg_db.flush()

    avaliar(cfg_db, agora + timedelta(minutes=1))

    assert [(n.tipo, n.destino_id) for n in alerta.notificacoes] == [
        ("ABERTURA", _padrao(cfg_db).id),
        ("RESOLUCAO", _padrao(cfg_db).id),
    ]


def test_regra_desligada_nao_abre_e_resolve_os_abertos_sem_aviso(cfg_db):
    agora = _agora(cfg_db)
    avaliar(cfg_db, agora)
    abertos = cfg_db.scalars(
        select(Alerta).where(Alerta.regra == "transferencia_erro", Alerta.status == "ABERTO")
    ).all()
    assert abertos
    _salvar(cfg_db, "transferencia_erro", ativo=False, destinos=[_padrao(cfg_db)])

    resultado = avaliar(cfg_db, agora + timedelta(minutes=1))

    assert resultado.desligadas == 2
    for alerta in abertos:
        assert alerta.status == "RESOLVIDO"
        assert [n.tipo for n in alerta.notificacoes] == ["ABERTURA"]


def test_mensagem_mostra_so_os_campos_marcados_na_ordem_do_catalogo():
    valores = {"nota": "NF 1", "origem": "1 - Matriz", "destino": "2 - Loja", "valor": "R$ 10,00"}
    corpo = montar_corpo("transferencia_erro", valores, ["valor", "nota"])
    assert corpo == "Nota: NF 1\nValor: R$ 10,00"


def test_mensagem_do_coi_tem_blocos_separados():
    valores = {"nota": "NF 1", "problemas": "• sem COI", "orientacao": "Corrija."}
    corpo = montar_corpo("transferencia_coi_errado", valores, ["nota", "problemas", "orientacao"])
    assert corpo == "Nota: NF 1\n\n• sem COI\n\nCorrija."


def test_despacho_usa_os_campos_e_o_chat_do_destino(cfg_db):
    grupo = _destino(cfg_db, "Grupo", "-100777")
    _salvar(cfg_db, "transferencia_erro", campos=["nota", "valor"], destinos=[grupo])
    agora = _agora(cfg_db)
    avaliar(cfg_db, agora)
    enviador = EnviadorFalso()

    processar_pendentes(cfg_db, enviador, agora, TZ, lote=100)

    envios = [(chat, t) for chat, t in enviador.envios if "com erro" in t]
    assert envios and all(chat == "-100777" for chat, _ in envios)
    assert all("Nota:" in t and "Origem:" not in t for _, t in envios)


def test_cada_canal_despacha_so_as_suas_notificacoes(cfg_db):
    grupo = _destino(cfg_db, "Grupo", "-100777")
    celular = _destino(cfg_db, "Celular", "5511987654321", canal="whatsapp")
    _salvar(cfg_db, "transferencia_erro", destinos=[grupo, celular])
    agora = _agora(cfg_db)
    avaliar(cfg_db, agora)
    canais = {n.destino_id: n.canal for n in _notificacoes(cfg_db, "transferencia_erro")}
    assert canais[grupo.id] == "telegram" and canais[celular.id] == "whatsapp"

    telegram, whatsapp = EnviadorFalso(), EnviadorFalso()
    whatsapp.canal = "whatsapp"
    processar_pendentes(cfg_db, telegram, agora, TZ, lote=100)
    processar_pendentes(cfg_db, whatsapp, agora, TZ, lote=100)

    erros_telegram = {chat for chat, t in telegram.envios if "com erro" in t}
    assert erros_telegram == {"-100777"}
    assert whatsapp.envios and {chat for chat, _ in whatsapp.envios} == {"5511987654321"}


def test_mudar_os_campos_vale_para_o_proximo_envio(cfg_db):
    _salvar(cfg_db, "transferencia_erro", campos=["nota"], destinos=[_padrao(cfg_db)])
    avaliar(cfg_db, _agora(cfg_db))
    alerta = cfg_db.scalars(select(Alerta).where(Alerta.regra == "transferencia_erro")).first()
    assert alerta is not None
    assert "Origem:" not in montar_texto(alerta, "ABERTURA", TZ, ["nota"])
    assert "Origem:" in montar_texto(alerta, "ABERTURA", TZ, ["nota", "origem"])


def test_alerta_antigo_sem_campos_usa_a_mensagem_gravada():
    alerta = Alerta(
        id=1,
        regra="transferencia_erro",
        severidade="ERROR",
        titulo="t",
        mensagem="antiga",
        detalhes={},
        aberto_em=__import__("datetime").datetime(2026, 1, 1, tzinfo=TZ),
    )
    assert "antiga" in montar_texto(alerta, "ABERTURA", TZ, ["nota"])


@pytest.fixture
def admin_api(cfg_db, criar_usuario_teste):
    admin = criar_usuario_teste("admin.alertas", "ADMIN", modulos=["ADMINISTRACAO"])
    app = app_com_sessao(cfg_db)
    yield TestClient(app, headers=token_para(app, admin))
    app.dependency_overrides.clear()


def test_api_exige_admin(cfg_db, criar_usuario_teste, client):
    assert client.get(URL).status_code == 401
    operador = criar_usuario_teste("op.cfg", "OPERADOR", modulos=["ALERTAS"])
    app = app_com_sessao(cfg_db)
    assert TestClient(app, headers=token_para(app, operador)).get(URL).status_code == 403


def test_api_lista_as_regras_no_padrao(admin_api, cfg_db):
    corpo = admin_api.get(URL).json()
    assert {r["regra"] for r in corpo["regras"]} == set(CATALOGO)
    atrasada = next(r for r in corpo["regras"] if r["regra"] == "transferencia_atrasada")
    assert atrasada["ativo"] and not atrasada["personalizada"]
    assert "parametros" not in atrasada
    assert atrasada["destinos"] == [_padrao(cfg_db).id]
    assert "emitida_por" in {c["chave"] for c in atrasada["campos_disponiveis"]}
    assert "emitida_por" not in atrasada["campos"]
    assert [d["nome"] for d in corpo["destinos"]] == ["Padrão"]


def test_api_cria_destino_e_configura_regra(admin_api):
    corpo = admin_api.post(
        f"{URL}/destinos",
        json={"nome": "Grupo Depósito", "chat_id": "-1001234567890", "severidade_minima": "ERROR"},
    )
    assert corpo.status_code == 201
    novo = next(d for d in corpo.json()["destinos"] if d["nome"] == "Grupo Depósito")

    resposta = admin_api.put(
        f"{URL}/regras/transferencia_atrasada",
        json={
            "ativo": True,
            "campos": ["emitida_por", "nota"],
            "destinos": [novo["id"]],
        },
    )
    assert resposta.status_code == 200
    regra = next(r for r in resposta.json()["regras"] if r["regra"] == "transferencia_atrasada")
    assert regra["personalizada"]
    assert regra["campos"] == ["nota", "emitida_por"]
    assert regra["destinos"] == [novo["id"]]

    restaurada = admin_api.delete(f"{URL}/regras/transferencia_atrasada").json()
    regra = next(r for r in restaurada["regras"] if r["regra"] == "transferencia_atrasada")
    assert not regra["personalizada"]


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        ({"ativo": True, "campos": ["inexistente"]}, "Campo desconhecido"),
        ({"ativo": True, "campos": [], "destinos": [999999]}, "Destino não encontrado"),
    ],
)
def test_api_recusa_configuracao_invalida(admin_api, corpo, trecho):
    resposta = admin_api.put(f"{URL}/regras/transferencia_atrasada", json=corpo)
    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"]


def test_api_regra_inexistente_404(admin_api):
    assert (
        admin_api.put(f"{URL}/regras/nao_existe", json={"ativo": True, "campos": []}).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("dados", "trecho"),
    [
        ({"nome": "X", "chat_id": "grupo da loja"}, "Chat do Telegram inválido"),
        ({"nome": "Padrão"}, "Já existe um destino"),
        ({"nome": "Y", "empresas": [999999]}, "Empresa não encontrada"),
        ({"nome": "Z", "canal": "whatsapp"}, "Informe o número do WhatsApp"),
        ({"nome": "Z", "canal": "whatsapp", "chat_id": "98765"}, "Número do WhatsApp inválido"),
        ({"nome": "Z", "canal": "whatsapp", "chat_id": "@canal"}, "Número do WhatsApp inválido"),
    ],
)
def test_api_recusa_destino_invalido(admin_api, dados, trecho):
    resposta = admin_api.post(f"{URL}/destinos", json=dados)
    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"]


def test_api_destino_com_historico_so_desliga(admin_api, cfg_db):
    avaliar(cfg_db, _agora(cfg_db))
    padrao = _padrao(cfg_db)

    assert admin_api.delete(f"{URL}/destinos/{padrao.id}").status_code == 409
    resposta = admin_api.put(
        f"{URL}/destinos/{padrao.id}", json={"nome": "Padrão", "chat_id": None, "ativo": False}
    )
    assert resposta.status_code == 200
    assert resposta.json()["destinos"][0]["ativo"] is False


def test_api_exclui_destino_sem_historico(admin_api, cfg_db):
    empresa = cfg_db.scalars(select(Empresa)).first()
    criado = admin_api.post(
        f"{URL}/destinos",
        json={"nome": "Temporário", "chat_id": "@canal_teste", "empresas": [empresa.id]},
    ).json()
    novo = next(d for d in criado["destinos"] if d["nome"] == "Temporário")
    assert novo["empresas"] == [empresa.id]

    resposta = admin_api.delete(f"{URL}/destinos/{novo['id']}")
    assert resposta.status_code == 200
    assert "Temporário" not in {d["nome"] for d in resposta.json()["destinos"]}


@pytest.mark.parametrize(
    ("digitado", "gravado"),
    [
        ("+55 (11) 98765-4321", "5511987654321"),
        ("11 98765-4321", "5511987654321"),
        ("5511987654321", "5511987654321"),
        ("+1 415 555 0100", "14155550100"),
    ],
)
def test_api_cria_destino_no_whatsapp_com_o_numero_so_em_digitos(admin_api, digitado, gravado):
    resposta = admin_api.post(
        f"{URL}/destinos", json={"nome": "Celular", "canal": "whatsapp", "chat_id": digitado}
    )
    assert resposta.status_code == 201, resposta.text
    novo = next(d for d in resposta.json()["destinos"] if d["nome"] == "Celular")
    assert novo["canal"] == "whatsapp" and novo["chat_id"] == gravado


def test_api_nao_muda_o_canal_de_destino_com_historico(admin_api, cfg_db):
    avaliar(cfg_db, _agora(cfg_db))
    padrao = _padrao(cfg_db)
    resposta = admin_api.put(
        f"{URL}/destinos/{padrao.id}",
        json={"nome": "Padrão", "canal": "whatsapp", "chat_id": "5511987654321"},
    )
    assert resposta.status_code == 422
    assert "cadastre outro destino" in resposta.json()["detail"]
