import importlib.util
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text

from app.database.models import AlertaConfiguracao, AlertaDestino, MensagemAvulsa, Notificacao
from app.notifications.outbox import processar_pendentes
from app.services import mensagens_avulsas as service
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

TZ = ZoneInfo("America/Porto_Velho")
URL = "/api/v1/admin/alertas/mensagens"
VERSOES = Path(__file__).resolve().parent.parent / "migrations" / "versions"

MIGRACOES = (
    ("0043_mensagens_avulsas.py", "SELECT to_regclass('mensagens_avulsas') IS NOT NULL"),
    (
        "0044_mensagens_repetidas.py",
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns"
        " WHERE table_schema = current_schema() AND table_name = 'mensagens_avulsas'"
        " AND column_name = 'horario')",
    ),
    (
        "0045_modelos_mensagem_avulsa.py",
        "SELECT to_regclass('modelos_mensagem_avulsa') IS NOT NULL",
    ),
)


class EnviadorFalso:
    def __init__(self, canal: str) -> None:
        self.canal = canal
        self.envios: list[tuple[str | None, str]] = []

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        self.envios.append((chat_id, texto))


def _garantir_migracao(db) -> None:
    for arquivo, aplicada in MIGRACOES:
        if db.scalar(text(aplicada)):
            continue
        spec = importlib.util.spec_from_file_location(f"migracao_{arquivo[:4]}", VERSOES / arquivo)
        assert spec and spec.loader
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        with Operations.context(MigrationContext.configure(db.connection())):
            modulo.upgrade()


@pytest.fixture
def msg_db(api_db):
    _garantir_migracao(api_db)
    api_db.execute(delete(AlertaConfiguracao))
    api_db.execute(delete(Notificacao))
    api_db.execute(delete(AlertaDestino))
    api_db.add_all(
        [
            AlertaDestino(nome="Padrão", chat_id=None),
            AlertaDestino(nome="Gerente", canal="whatsapp", chat_id="5511999990000"),
            AlertaDestino(nome="Desligado", canal="whatsapp", chat_id="5511988880000", ativo=False),
        ]
    )
    api_db.flush()
    return api_db


def _destino(db, nome: str) -> AlertaDestino:
    return db.scalar(select(AlertaDestino).where(AlertaDestino.nome == nome))


@pytest.fixture
def admin(msg_db, criar_usuario_teste):
    return criar_usuario_teste("admin.msg", "ADMIN", modulos=["ADMINISTRACAO"])


@pytest.fixture
def admin_api(msg_db, admin):
    app = app_com_sessao(msg_db)
    yield TestClient(app, headers=token_para(app, admin))
    app.dependency_overrides.clear()


def _criar(db, admin, agora, **kw):
    return service.criar(
        db,
        texto=kw.get("texto", "Reunião às 8h"),
        destinos=kw.get("destinos", [_destino(db, "Gerente").id]),
        agendada_para=kw.get("agendada_para"),
        usuario=admin,
        agora=agora,
        tz=TZ,
    )


def test_agora_sai_no_proximo_ciclo_com_o_texto_como_foi_escrito(msg_db, admin):
    agora = datetime.now(UTC)
    texto = "Atenção equipe\n\nInventário amanhã às 7h."
    _criar(msg_db, admin, agora, texto=texto)
    whatsapp = EnviadorFalso("whatsapp")
    resultado = processar_pendentes(msg_db, whatsapp, agora, TZ)
    assert resultado.enviadas == 1
    assert whatsapp.envios == [("5511999990000", texto)]


def test_agendada_so_sai_quando_chega_a_hora(msg_db, admin):
    agora = datetime.now(UTC)
    marcada = agora + timedelta(hours=3)
    _criar(msg_db, admin, agora, agendada_para=marcada)
    whatsapp = EnviadorFalso("whatsapp")
    assert processar_pendentes(msg_db, whatsapp, agora, TZ).enviadas == 0

    assert processar_pendentes(msg_db, whatsapp, marcada + timedelta(minutes=1), TZ).enviadas == 1


def test_hora_sem_fuso_e_hora_local_da_empresa(msg_db, admin):
    agora = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    mensagem = _criar(msg_db, admin, agora, agendada_para=datetime(2026, 11, 6, 8, 0))
    assert mensagem.agendada_para == datetime(2026, 11, 6, 8, 0, tzinfo=TZ)


def test_cada_destino_sai_pelo_seu_canal(msg_db, admin):
    agora = datetime.now(UTC)
    _criar(
        msg_db,
        admin,
        agora,
        destinos=[_destino(msg_db, "Gerente").id, _destino(msg_db, "Padrão").id],
    )
    whatsapp, telegram = EnviadorFalso("whatsapp"), EnviadorFalso("telegram")
    assert processar_pendentes(msg_db, whatsapp, agora, TZ).enviadas == 1
    assert processar_pendentes(msg_db, telegram, agora, TZ).enviadas == 1
    assert telegram.envios == [(None, "Reunião às 8h")]


@pytest.mark.parametrize(
    ("kw", "trecho"),
    [
        ({"texto": "   "}, "Escreva"),
        ({"texto": "x" * 4001}, "4000"),
        ({"destinos": []}, "pelo menos um"),
        ({"destinos": [999999]}, "inexistente"),
        ({"agendada_para": datetime(2020, 1, 1, tzinfo=UTC)}, "já passaram"),
    ],
)
def test_entradas_invalidas(msg_db, admin, kw, trecho):
    with pytest.raises(service.MensagemInvalida, match=trecho):
        _criar(msg_db, admin, datetime.now(UTC), **kw)


def test_destino_desligado_e_recusado(msg_db, admin):
    with pytest.raises(service.MensagemInvalida, match="desligado"):
        _criar(msg_db, admin, datetime.now(UTC), destinos=[_destino(msg_db, "Desligado").id])


def test_cancelar_descarta_o_que_nao_saiu(msg_db, admin):
    agora = datetime.now(UTC)
    mensagem = _criar(msg_db, admin, agora, agendada_para=agora + timedelta(hours=1))
    service.cancelar(msg_db, mensagem.id, agora)
    whatsapp = EnviadorFalso("whatsapp")
    assert processar_pendentes(msg_db, whatsapp, agora + timedelta(hours=2), TZ).enviadas == 0
    assert whatsapp.envios == []
    assert {n.status for n in mensagem.notificacoes} == {"DESCARTADA"}
    with pytest.raises(service.NadaParaCancelar):
        service.cancelar(msg_db, mensagem.id, agora)


def test_api_cria_lista_e_cancela(admin_api, msg_db):
    gerente = _destino(msg_db, "Gerente").id
    depois_de_amanha = (datetime.now(TZ) + timedelta(days=2)).strftime("%Y-%m-%dT08:00:00")
    resposta = admin_api.post(
        URL,
        json={
            "texto": "Fechamento do mês hoje",
            "destinos": [gerente],
            "agendada_para": depois_de_amanha,
        },
    )
    assert resposta.status_code == 201, resposta.text
    criada = resposta.json()
    assert criada["criada_por"] == "Admin.Msg"
    assert criada["envios"][0]["destino_nome"] == "Gerente"
    assert criada["envios"][0]["status"] == "PENDENTE"

    lista = admin_api.get(URL).json()
    assert [m["id"] for m in lista][0] == criada["id"]

    cancelada = admin_api.delete(f"{URL}/{criada['id']}")
    assert cancelada.status_code == 200
    assert cancelada.json()["envios"][0]["status"] == "DESCARTADA"
    assert admin_api.delete(f"{URL}/{criada['id']}").status_code == 409
    assert admin_api.delete(f"{URL}/999999").status_code == 404


def test_api_recusa_entrada_invalida_com_422(admin_api, msg_db):
    assert admin_api.post(URL, json={"texto": "oi", "destinos": [999999]}).status_code == 422
    assert admin_api.post(URL, json={"texto": "", "destinos": [1]}).status_code == 422


def test_api_exige_admin(msg_db, criar_usuario_teste):
    operador = criar_usuario_teste("op.msg", "OPERADOR", modulos=["ALERTAS"])
    app = app_com_sessao(msg_db)
    cliente = TestClient(app, headers=token_para(app, operador))
    assert cliente.post(URL, json={"texto": "oi", "destinos": [1]}).status_code == 403
    assert msg_db.scalar(select(MensagemAvulsa)) is None


def _repetida(db, admin, agora, **kw):
    return service.criar(
        db,
        texto=kw.get("texto", "Faturamento líquido: {faturamento_liquido}\nRecebido: {recebido}"),
        destinos=kw.get("destinos", [_destino(db, "Gerente").id]),
        agendada_para=None,
        usuario=admin,
        agora=agora,
        tz=TZ,
        horario=kw.get("horario", time(18, 0)),
        dias_semana=kw.get("dias_semana", service.TODOS_OS_DIAS),
    )


def test_repetida_marca_o_proximo_envio_e_nao_enfileira_na_criacao(msg_db, admin):

    agora = datetime(2026, 11, 5, 10, 0, tzinfo=TZ)
    mensagem = _repetida(msg_db, admin, agora)
    assert mensagem.agendada_para == datetime(2026, 11, 5, 18, 0, tzinfo=TZ)
    assert mensagem.notificacoes == []

    depois = _repetida(msg_db, admin, datetime(2026, 11, 5, 19, 0, tzinfo=TZ))
    assert depois.agendada_para == datetime(2026, 11, 6, 18, 0, tzinfo=TZ)


def test_repetida_pula_os_dias_nao_marcados(msg_db, admin):

    agora = datetime(2026, 11, 6, 19, 0, tzinfo=TZ)
    mensagem = _repetida(msg_db, admin, agora, dias_semana=[1, 2, 3, 4, 5])
    assert mensagem.agendada_para == datetime(2026, 11, 9, 18, 0, tzinfo=TZ)


def test_worker_enfileira_a_vencida_passa_para_amanha_e_troca_as_variaveis(msg_db, admin):
    criada = datetime(2026, 11, 5, 10, 0, tzinfo=TZ)
    mensagem = _repetida(msg_db, admin, criada)
    na_hora = datetime(2026, 11, 5, 18, 0, 30, tzinfo=TZ)

    assert service.gerar_repetidas(msg_db, na_hora, TZ) == 1
    assert mensagem.agendada_para == datetime(2026, 11, 6, 18, 0, tzinfo=TZ)
    assert service.gerar_repetidas(msg_db, na_hora, TZ) == 0

    whatsapp = EnviadorFalso("whatsapp")
    assert processar_pendentes(msg_db, whatsapp, na_hora, TZ).enviadas == 1
    ((numero, texto),) = whatsapp.envios
    assert numero == "5511999990000"
    assert re.fullmatch(r"Faturamento líquido: R\$ [\d.]+,\d\d\nRecebido: R\$ [\d.]+,\d\d", texto)


def test_worker_parado_alem_da_validade_pula_o_dia(msg_db, admin):
    mensagem = _repetida(msg_db, admin, datetime(2026, 11, 5, 10, 0, tzinfo=TZ))
    muito_depois = datetime(2026, 11, 6, 9, 0, tzinfo=TZ)
    assert service.gerar_repetidas(msg_db, muito_depois, TZ) == 0
    assert mensagem.agendada_para == datetime(2026, 11, 6, 18, 0, tzinfo=TZ)


def test_parar_a_repetida(msg_db, admin):
    agora = datetime(2026, 11, 5, 10, 0, tzinfo=TZ)
    mensagem = _repetida(msg_db, admin, agora)
    service.cancelar(msg_db, mensagem.id, agora)
    assert service.gerar_repetidas(msg_db, datetime(2026, 11, 5, 18, 1, tzinfo=TZ), TZ) == 0
    with pytest.raises(service.NadaParaCancelar):
        service.cancelar(msg_db, mensagem.id, agora)


def test_variavel_desconhecida_e_recusada(msg_db, admin):
    with pytest.raises(service.MensagemInvalida, match=r"\{lucro\}"):
        _criar(msg_db, admin, datetime.now(UTC), texto="Lucro: {lucro}")


def test_previa_usa_os_valores_de_agora(msg_db):
    agora = datetime(2026, 11, 5, 18, 0, tzinfo=TZ)
    texto = service.previa(msg_db, "{data} {hora}: {notas} notas", agora, TZ)
    assert re.fullmatch(r"05/11/2026 18:00: \d+ notas", texto)


def test_api_cria_repetida_e_lista_variaveis_e_previa(admin_api, msg_db):
    variaveis = admin_api.get(f"{URL}/variaveis").json()
    assert {"faturamento_liquido", "recebido"} <= {v["chave"] for v in variaveis}

    previa = admin_api.post(f"{URL}/previa", json={"texto": "Hoje: {faturamento_liquido}"})
    assert previa.status_code == 200
    assert previa.json()["texto"].startswith("Hoje: R$ ")
    assert admin_api.post(f"{URL}/previa", json={"texto": "{xyz}"}).status_code == 422

    resposta = admin_api.post(
        URL,
        json={
            "texto": "Recebido: {recebido}",
            "destinos": [_destino(msg_db, "Gerente").id],
            "horario": "18:00",
            "dias_semana": [1, 2, 3, 4, 5, 6],
        },
    )
    assert resposta.status_code == 201, resposta.text
    criada = resposta.json()
    assert criada["horario"] == "18:00:00"
    assert criada["dias_semana"] == [1, 2, 3, 4, 5, 6]
    assert criada["envios"] == []
    assert admin_api.delete(f"{URL}/{criada['id']}").status_code == 200


def test_salvar_modelo_com_o_mesmo_nome_troca_o_texto(msg_db, admin):
    service.salvar_modelo(
        msg_db, nome="Resumo das 18h", texto="Líquido: {faturamento_liquido}", usuario=admin
    )
    service.salvar_modelo(
        msg_db, nome="  resumo   DAS 18h ", texto="Recebido: {recebido}", usuario=admin
    )
    (modelo,) = service.listar_modelos(msg_db)
    assert modelo.nome == "resumo DAS 18h"
    assert modelo.texto == "Recebido: {recebido}"
    assert modelo.atualizado_por == "Admin.Msg"


@pytest.mark.parametrize(
    ("nome", "texto", "trecho"),
    [
        ("", "oi", "nome"),
        ("x" * 81, "oi", "80"),
        ("Ok", " ", "Escreva"),
        ("Ok", "{lucro}", r"\{lucro\}"),
    ],
)
def test_modelo_invalido(msg_db, admin, nome, texto, trecho):
    with pytest.raises(service.MensagemInvalida, match=trecho):
        service.salvar_modelo(msg_db, nome=nome, texto=texto, usuario=admin)


def test_api_salva_lista_e_exclui_modelos(admin_api, msg_db):
    url = f"{URL}/modelos"
    assert admin_api.get(url).json() == []
    salvos = admin_api.post(
        url, json={"nome": "Bom dia", "texto": "Ontem: {faturamento_liquido_ontem}"}
    )
    assert salvos.status_code == 200, salvos.text
    salvos = admin_api.post(url, json={"nome": "Abertura", "texto": "Loja aberta"}).json()
    assert [m["nome"] for m in salvos] == ["Abertura", "Bom dia"]
    assert admin_api.post(url, json={"nome": "X", "texto": "{xyz}"}).status_code == 422

    restantes = admin_api.delete(f"{url}/{salvos[0]['id']}")
    assert [m["nome"] for m in restantes.json()] == ["Bom dia"]
    assert admin_api.delete(f"{url}/999999").status_code == 404
