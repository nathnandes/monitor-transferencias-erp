from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import Alerta, Notificacao
from app.notifications.enviador import ErroEnvio
from app.notifications.mensagens import montar_texto
from app.notifications.outbox import MAX_TENTATIVAS, VALIDADE, enfileirar, processar_pendentes
from app.rules.regras import Ocorrencia
from app.workers.monitor import executar_ciclo

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


class EnviadorFalso:
    canal = "telegram"

    def __init__(self, falhas: list[ErroEnvio] | None = None) -> None:
        self.enviados: list[str] = []

        self.chats: list[str | None] = []
        self.falhas = list(falhas or [])

    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        if self.falhas:
            raise self.falhas.pop(0)
        self.enviados.append(texto)
        self.chats.append(chat_id)


def _alerta(db: Session, chave: str = "teste:1", severidade: str = "ERROR") -> Alerta:
    alerta = Alerta(
        regra="teste",
        chave=chave,
        severidade=severidade,
        status="ABERTO",
        titulo="Transferência X com erro",
        mensagem="Origem: 01\nDestino: 02",
        aberto_em=AGORA,
        visto_em=AGORA,
    )
    db.add(alerta)
    db.flush()
    return alerta


def test_texto_de_abertura_escalada_e_resolucao():
    alerta = Alerta(
        id=7,
        severidade="CRITICAL",
        titulo="Transferência X pendente há 30h",
        mensagem="Origem: 01",
        aberto_em=AGORA,
        resolvido_em=AGORA + timedelta(hours=2),
    )
    abertura = montar_texto(alerta, "ABERTURA", TZ)
    assert abertura.startswith("🚨 CRITICAL: Transferência X pendente há 30h")
    assert "Origem: 01" in abertura and "02/10 09:00" in abertura and "#7" in abertura

    assert montar_texto(alerta, "ESCALADA", TZ).startswith("🚨 AGRAVOU PARA CRITICAL:")

    resolucao = montar_texto(alerta, "RESOLUCAO", TZ)
    assert resolucao.startswith("✅ RESOLVIDO:")
    assert "02/10 09:00" in resolucao and "02/10 11:00" in resolucao


def test_texto_respeita_limite_do_telegram():
    alerta = Alerta(id=1, severidade="ERROR", titulo="t", mensagem="x" * 10_000, aberto_em=AGORA)
    assert len(montar_texto(alerta, "ABERTURA", TZ)) == 4096


integration = pytest.mark.integration


@pytest.fixture
def db(db: Session) -> Session:
    db.execute(delete(Alerta))
    return db


@integration
def test_envia_pendente_e_marca_como_enviada(db):
    alerta = _alerta(db)
    n = enfileirar(db, alerta, "ABERTURA", AGORA)
    enviador = EnviadorFalso()

    resultado = processar_pendentes(db, enviador, AGORA, TZ)

    assert resultado.enviadas == 1
    assert n.status == "ENVIADA" and n.enviada_em == AGORA and n.tentativas == 1
    assert len(enviador.enviados) == 1 and "Transferência X com erro" in enviador.enviados[0]
    assert processar_pendentes(db, enviador, AGORA, TZ).enviadas == 0


@integration
def test_falha_transitoria_reagenda_com_espera_exponencial(db):
    n = enfileirar(db, _alerta(db), "ABERTURA", AGORA)
    enviador = EnviadorFalso([ErroEnvio("timeout", transitorio=True)] * 2)

    processar_pendentes(db, enviador, AGORA, TZ)
    assert n.status == "PENDENTE" and n.tentativas == 1
    assert n.proxima_tentativa_em == AGORA + timedelta(minutes=1)
    assert processar_pendentes(db, enviador, AGORA, TZ).reagendadas == 0

    processar_pendentes(db, enviador, n.proxima_tentativa_em, TZ)
    assert n.tentativas == 2
    segunda = n.proxima_tentativa_em

    processar_pendentes(db, enviador, segunda, TZ)
    assert n.status == "ENVIADA" and n.ultimo_erro is None


@integration
def test_falha_permanente_desiste_na_hora(db):
    n = enfileirar(db, _alerta(db), "ABERTURA", AGORA)
    erro = ErroEnvio("Telegram respondeu 401: Unauthorized", transitorio=False)

    resultado = processar_pendentes(db, EnviadorFalso([erro]), AGORA, TZ)

    assert resultado.falhas == 1
    assert n.status == "FALHA" and "401" in (n.ultimo_erro or "")


@integration
def test_desiste_apos_o_maximo_de_tentativas(db):
    n = enfileirar(db, _alerta(db), "ABERTURA", AGORA)
    enviador = EnviadorFalso([ErroEnvio("rede", transitorio=True)] * MAX_TENTATIVAS)
    momento = AGORA
    for _ in range(MAX_TENTATIVAS):
        processar_pendentes(db, enviador, momento, TZ)
        momento = n.proxima_tentativa_em
    assert n.status == "FALHA" and n.tentativas == MAX_TENTATIVAS


@integration
def test_notificacao_velha_e_descartada_sem_enviar(db):
    n = enfileirar(db, _alerta(db), "ABERTURA", AGORA)
    enviador = EnviadorFalso()

    processar_pendentes(db, enviador, AGORA + VALIDADE + timedelta(seconds=1), TZ)

    assert n.status == "DESCARTADA" and enviador.enviados == []


@integration
def test_abertura_de_alerta_ja_resolvido_e_a_resolucao_dela_sao_descartadas(db):
    alerta = _alerta(db)
    abertura = enfileirar(db, alerta, "ABERTURA", AGORA)
    alerta.status, alerta.resolvido_em = "RESOLVIDO", AGORA
    resolucao = enfileirar(db, alerta, "RESOLUCAO", AGORA)
    db.flush()
    enviador = EnviadorFalso()

    processar_pendentes(db, enviador, AGORA, TZ)

    assert (abertura.status, resolucao.status) == ("DESCARTADA", "DESCARTADA")
    assert enviador.enviados == []


@integration
def test_resolucao_sai_depois_da_abertura_enviada(db):
    alerta = _alerta(db)
    enfileirar(db, alerta, "ABERTURA", AGORA)
    processar_pendentes(db, EnviadorFalso(), AGORA, TZ)
    alerta.status, alerta.resolvido_em = "RESOLVIDO", AGORA + timedelta(minutes=3)
    resolucao = enfileirar(db, alerta, "RESOLUCAO", AGORA + timedelta(minutes=3))
    enviador = EnviadorFalso()

    processar_pendentes(db, enviador, AGORA + timedelta(minutes=3), TZ)

    assert resolucao.status == "ENVIADA"
    assert enviador.enviados[0].startswith("✅ RESOLVIDO")


class EnviadorQueQuebra(EnviadorFalso):
    def enviar(self, texto: str, chat_id: str | None = None) -> None:
        if self.enviados:
            raise RuntimeError("bug no canal")
        super().enviar(texto, chat_id)


@integration
def test_erro_inesperado_numa_notificacao_nao_derruba_o_lote(db):
    primeira = enfileirar(db, _alerta(db, chave="teste:1"), "ABERTURA", AGORA)
    segunda = enfileirar(db, _alerta(db, chave="teste:2"), "ABERTURA", AGORA)
    db.flush()
    enviador = EnviadorQueQuebra()

    resultado = processar_pendentes(db, enviador, AGORA, TZ)

    assert (resultado.enviadas, resultado.falhas) == (1, 1)
    assert primeira.status == "ENVIADA"
    assert segunda.status == "FALHA" and "bug no canal" in (segunda.ultimo_erro or "")
    assert processar_pendentes(db, enviador, AGORA, TZ).enviadas == 0


@integration
def test_lote_limita_envios_por_ciclo(db):
    for i in range(5):
        enfileirar(db, _alerta(db, chave=f"teste:{i}"), "ABERTURA", AGORA)
    enviador = EnviadorFalso()

    assert processar_pendentes(db, enviador, AGORA, TZ, lote=3).enviadas == 3
    assert processar_pendentes(db, enviador, AGORA, TZ, lote=3).enviadas == 2


def _fabrica(db: Session):
    conexao = db.connection()
    return lambda: Session(bind=conexao, join_transaction_mode="create_savepoint")


@integration
def test_ciclo_do_worker_abre_alertas_e_despacha(api_db):
    enviador = EnviadorFalso()
    agora = datetime.now(UTC)

    resultado = executar_ciclo(_fabrica(api_db), enviador, TZ, agora=lambda: agora)

    assert resultado.avaliacao.abertos > 0
    assert resultado.despacho is not None and resultado.despacho.enviadas == min(
        resultado.avaliacao.abertos, 10
    )
    assert len(enviador.enviados) == resultado.despacho.enviadas


@integration
def test_ciclo_sem_enviador_so_avalia(api_db):
    resultado = executar_ciclo(_fabrica(api_db), None, TZ)

    assert resultado.avaliacao.abertos > 0
    assert resultado.despacho is None
    pendentes = api_db.scalars(select(Notificacao).where(Notificacao.status == "PENDENTE")).all()
    assert len(pendentes) == resultado.avaliacao.abertos


def test_worker_sobrevive_a_um_ciclo_com_erro(monkeypatch, caplog):
    import threading

    from app.core.config import Settings
    from app.workers import monitor

    chamadas = []

    def ciclo_que_falha(*args, **kwargs):
        chamadas.append(1)
        raise RuntimeError("banco fora")

    monkeypatch.setattr(monitor, "executar_ciclo", ciclo_que_falha)
    parar = threading.Event()

    monitor.rodar(Settings(), lambda: None, None, parar, uma_vez=True)  # type: ignore[arg-type]

    assert chamadas == [1]
    assert "ciclo do monitor falhou" in caplog.text


def test_ocorrencia_tem_detalhes_vazios_por_padrao():
    assert Ocorrencia("r", "r:1", "ERROR", "t", "m").detalhes == {}


@integration
def test_main_uma_vez_roda_um_ciclo_com_telegram_desligado(api_db, monkeypatch, caplog):
    import logging

    from app.database import session as modulo_sessao
    from app.workers import monitor

    monkeypatch.setattr(modulo_sessao, "SessionLocal", _fabrica(api_db))

    monkeypatch.setattr(monitor.signal, "signal", lambda *args: None)

    from app.core.config import Settings

    monkeypatch.setattr(monitor, "get_settings", lambda: Settings(_env_file=None))  # type: ignore[call-arg]
    with caplog.at_level(logging.INFO, logger="app"):
        assert monitor.main(["--uma-vez"]) == 0

    assert "telegram=desligado" in caplog.text
    assert "monitor encerrado" in caplog.text
    abertos = api_db.scalars(select(Alerta).where(Alerta.status == "ABERTO")).all()
    assert abertos
