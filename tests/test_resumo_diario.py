from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.database.models import ResumoDiario
from app.notifications.enviador import ErroEnvio
from app.notifications.resumo_diario import JANELA, montar_resumo, processar_resumo_diario
from app.rules.motor import avaliar
from app.workers.monitor import executar_ciclo
from tests.test_notificacoes import EnviadorFalso, _fabrica

pytestmark = pytest.mark.integration

SETTINGS = get_settings().model_copy(
    update={"tz": "America/Porto_Velho", "resumo_diario_horario": "07:00"}
)
TZ = ZoneInfo("America/Porto_Velho")
SETE_HORAS = datetime(2026, 10, 14, 11, 0, tzinfo=UTC)
DIA = date(2026, 10, 14)


def _resumos(db) -> list[ResumoDiario]:
    db.expire_all()
    return list(db.scalars(select(ResumoDiario)))


def test_antes_do_horario_nao_faz_nada(db_vazio):
    enviador = EnviadorFalso()
    antes = SETE_HORAS - timedelta(minutes=1)
    assert processar_resumo_diario(db_vazio, enviador, antes, SETTINGS) is None
    assert _resumos(db_vazio) == [] and enviador.enviados == []


def test_no_horario_envia_uma_vez_por_dia(db_vazio):
    enviador = EnviadorFalso()

    assert processar_resumo_diario(db_vazio, enviador, SETE_HORAS, SETTINGS) == "ENVIADO"

    depois = SETE_HORAS + timedelta(minutes=1)
    assert processar_resumo_diario(db_vazio, enviador, depois, SETTINGS) is None

    assert len(enviador.enviados) == 1
    texto = enviador.enviados[0]
    assert texto.startswith("☀️ Resumo de 14/10/2026")
    for trecho in ("Alertas abertos", "• nenhum ✅", "Transferências", "Vendas de ontem (13/10)"):
        assert trecho in texto
    [resumo] = _resumos(db_vazio)
    assert (resumo.dia, resumo.status, resumo.tentativas) == (DIA, "ENVIADO", 1)


def test_falha_transitoria_tenta_de_novo_com_o_mesmo_texto(db_vazio):
    enviador = EnviadorFalso([ErroEnvio("timeout", transitorio=True)])

    assert processar_resumo_diario(db_vazio, enviador, SETE_HORAS, SETTINGS) == "PENDENTE"

    cedo = SETE_HORAS + timedelta(minutes=1)
    assert processar_resumo_diario(db_vazio, enviador, cedo, SETTINGS) is None
    tarde = SETE_HORAS + timedelta(minutes=10)
    assert processar_resumo_diario(db_vazio, enviador, tarde, SETTINGS) == "ENVIADO"

    [resumo] = _resumos(db_vazio)
    assert enviador.enviados == [resumo.texto]
    assert resumo.tentativas == 2 and resumo.ultimo_erro is None


def test_falha_permanente_desiste(db_vazio):
    enviador = EnviadorFalso([ErroEnvio("chat nao encontrado", transitorio=False)])
    assert processar_resumo_diario(db_vazio, enviador, SETE_HORAS, SETTINGS) == "FALHA"
    [resumo] = _resumos(db_vazio)
    assert resumo.ultimo_erro == "chat nao encontrado"


def test_fora_da_janela_nao_manda_o_bom_dia_a_noite(db_vazio):
    enviador = EnviadorFalso()
    noite = SETE_HORAS + JANELA + timedelta(minutes=1)
    assert processar_resumo_diario(db_vazio, enviador, noite, SETTINGS) is None
    assert _resumos(db_vazio) == []


def test_horario_vazio_desliga(db_vazio):
    desligado = SETTINGS.model_copy(update={"resumo_diario_horario": ""})
    assert processar_resumo_diario(db_vazio, EnviadorFalso(), SETE_HORAS, desligado) is None


def test_resumo_sobre_o_seed_conta_alertas_e_transferencias(api_db):
    agora = api_db.scalar(select(func.now()))
    avaliar(api_db, agora)

    texto = montar_resumo(api_db, agora, SETTINGS)

    assert "• nenhum ✅" not in texto
    assert "com COI errado:" in texto and "sem entrada no destino:" in texto


def test_ciclo_do_worker_manda_o_resumo_com_o_telegram_ligado(api_db):
    enviador = EnviadorFalso()
    resultado = executar_ciclo(
        _fabrica(api_db), enviador, TZ, agora=lambda: SETE_HORAS, settings=SETTINGS
    )

    assert resultado.resumo == "ENVIADO"
    assert any(t.startswith("☀️ Resumo de") for t in enviador.enviados)
