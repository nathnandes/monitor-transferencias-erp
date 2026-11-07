from datetime import UTC, datetime, timedelta

import pytest

from app.database.models import Sincronizacao
from app.rules import regras
from app.rules.motor import avaliar

pytestmark = pytest.mark.integration

AGORA = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
M = timedelta(minutes=1)
SO_ESTA = {"sincronizacao_parada": regras.sincronizacao_parada}


def _sync(db, tipo: str, ha: timedelta, status: str = "sucesso") -> None:
    fim = AGORA - ha
    db.add(Sincronizacao(tipo=tipo, inicio=fim - M, fim=fim, status=status))
    db.flush()


def _por_tipo(db) -> dict[str, str]:
    return {o.detalhes["tipo"]: o.severidade for o in regras.sincronizacao_parada(db, AGORA)}


def test_recente_nao_alerta(db_vazio):
    _sync(db_vazio, "transferencias", 20 * M)
    assert _por_tipo(db_vazio) == {}


def test_parada_avisa_e_depois_fica_critica(db_vazio):
    _sync(db_vazio, "transferencias", 45 * M)
    _sync(db_vazio, "estoque", 3 * 60 * M)
    assert _por_tipo(db_vazio) == {"transferencias": "WARNING", "estoque": "CRITICAL"}


def test_parcial_conta_como_concluida_e_erro_nao(db_vazio):
    _sync(db_vazio, "vendas", 10 * M, status="parcial")
    _sync(db_vazio, "precos", 2 * 60 * M)
    _sync(db_vazio, "precos", 5 * M, status="erro")
    assert _por_tipo(db_vazio) == {"precos": "CRITICAL"}


def test_tipo_que_nunca_concluiu_nao_alerta(db_vazio):
    _sync(db_vazio, "estoque", 5 * M, status="erro")
    assert _por_tipo(db_vazio) == {}


def test_intervalo_longo_aumenta_o_limite(db_vazio, monkeypatch):
    configuracao = regras.get_settings().model_copy(update={"sync_vendas_intervalo_segundos": 3600})
    monkeypatch.setattr(regras, "get_settings", lambda: configuracao)
    _sync(db_vazio, "vendas", 2 * 60 * M)
    assert _por_tipo(db_vazio) == {}


def test_tipo_so_sob_pedido_nao_alerta(db_vazio, monkeypatch):
    configuracao = regras.get_settings().model_copy(update={"sync_estoque_intervalo_segundos": 0})
    monkeypatch.setattr(regras, "get_settings", lambda: configuracao)
    _sync(db_vazio, "estoque", 10 * 60 * M)
    assert _por_tipo(db_vazio) == {}


def test_motor_abre_e_resolve_quando_volta_a_concluir(db_vazio):
    _sync(db_vazio, "transferencias", 45 * M)
    resultado = avaliar(db_vazio, AGORA, regras=SO_ESTA)
    assert resultado.abertos == 1

    _sync(db_vazio, "transferencias", 1 * M)
    resultado = avaliar(db_vazio, AGORA, regras=SO_ESTA)
    assert resultado.resolvidos == 1
