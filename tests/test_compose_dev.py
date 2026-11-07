import re
from pathlib import Path

COMPOSE = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text(
    encoding="utf-8"
)


def _portas_publicadas() -> list[str]:
    return re.findall(r'^\s*-\s*"([^"]*:\d+)"\s*$', COMPOSE, flags=re.MULTILINE)


def test_portas_so_no_loopback():
    portas = _portas_publicadas()
    assert portas, "nenhuma porta encontrada: o formato do compose mudou?"
    assert [p for p in portas if not p.startswith("127.0.0.1:")] == []


def test_senha_do_banco_sem_valor_padrao_conhecido():
    assert "erp_local_dev" not in COMPOSE
    assert "${POSTGRES_PASSWORD:?" in COMPOSE
