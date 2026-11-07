from datetime import UTC, datetime, timedelta

import pytest

from app.database.models import Alerta, Empresa, Sincronizacao
from app.rules import regras
from app.rules.motor import avaliar

pytestmark = pytest.mark.integration

AGORA = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
M = timedelta(minutes=1)
SO_ESTA = {"sincronizacao_erro": regras.sincronizacao_erro}


@pytest.fixture
def loja(db_vazio) -> Empresa:
    empresa = Empresa(codigo="02", nome="Loja 2", id_erp="2", ambiente="teste-regra")
    db_vazio.add(empresa)
    db_vazio.flush()
    return empresa


def _sync(db, empresa: Empresa, tipo: str, ha: timedelta, status: str) -> None:
    inicio = AGORA - ha
    db.add(
        Sincronizacao(
            empresa_id=empresa.id, tipo=tipo, inicio=inicio, fim=inicio + M, status=status
        )
    )
    db.flush()


def _chaves(db) -> set[str]:
    return {o.chave for o in regras.sincronizacao_erro(db, AGORA)}


def test_sucesso_de_outro_tipo_nao_esconde_o_erro_do_estoque(db_vazio, loja):

    _sync(db_vazio, loja, "estoque", 6 * M, "erro")
    _sync(db_vazio, loja, "vendas", 3 * M, "sucesso")

    assert _chaves(db_vazio) == {f"sincronizacao_erro:{loja.id}:estoque"}


def test_cada_tipo_com_erro_abre_o_seu_alerta(db_vazio, loja):
    _sync(db_vazio, loja, "estoque", 6 * M, "erro")
    _sync(db_vazio, loja, "precos", 3 * M, "erro")

    assert _chaves(db_vazio) == {
        f"sincronizacao_erro:{loja.id}:estoque",
        f"sincronizacao_erro:{loja.id}:precos",
    }


def test_alerta_nao_pisca_quando_os_tipos_se_alternam(db_vazio, loja):
    _sync(db_vazio, loja, "estoque", 20 * M, "erro")
    avaliar(db_vazio, AGORA - 19 * M, regras=SO_ESTA)
    _sync(db_vazio, loja, "vendas", 15 * M, "sucesso")
    avaliar(db_vazio, AGORA - 14 * M, regras=SO_ESTA)
    _sync(db_vazio, loja, "estoque", 10 * M, "erro")
    avaliar(db_vazio, AGORA - 9 * M, regras=SO_ESTA)

    alertas = db_vazio.query(Alerta).filter_by(regra="sincronizacao_erro").all()
    assert [(a.status, [n.tipo for n in a.notificacoes]) for a in alertas] == [
        ("ABERTO", ["ABERTURA"])
    ]


def test_nova_execucao_do_mesmo_tipo_com_sucesso_resolve(db_vazio, loja):
    _sync(db_vazio, loja, "estoque", 10 * M, "erro")
    _sync(db_vazio, loja, "estoque", 5 * M, "sucesso")

    assert _chaves(db_vazio) == set()
