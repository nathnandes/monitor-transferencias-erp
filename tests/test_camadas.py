import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "src" / "app"


def _imports(pacote: str) -> list[tuple[str, str]]:
    achados = []
    for arquivo in sorted((APP / pacote).rglob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
                modulos = [no.module] + [f"{no.module}.{a.name}" for a in no.names]
            elif isinstance(no, ast.Import):
                modulos = [a.name for a in no.names]
            else:
                continue
            nome = str(arquivo.relative_to(APP.parent))
            achados += [(nome, m) for m in modulos if m.startswith("app.")]
    return achados


@pytest.mark.parametrize(
    ("pacote", "proibidos"),
    [
        ("dominio", ("app.",)),
        ("database", ("app.services", "app.api", "app.sync")),
        ("sync", ("app.services", "app.api")),
    ],
)
def test_camada_nao_importa_as_de_cima(pacote, proibidos):
    violacoes = [
        f"{arquivo} importa {modulo}"
        for arquivo, modulo in _imports(pacote)
        if modulo.startswith(proibidos)
    ]
    assert violacoes == []


def test_anomalias_so_importa_o_proprio_pacote():
    violacoes = [
        f"{arquivo} importa {modulo}"
        for arquivo, modulo in _imports("anomalias")
        if not modulo.startswith("app.anomalias")
    ]
    assert violacoes == []


def test_router_nao_importa_nome_privado_de_outro_router():
    violacoes = [
        f"{arquivo} importa {modulo}"
        for arquivo, modulo in _imports("api")
        if modulo.startswith("app.api.v1.") and modulo.rsplit(".", 1)[-1].startswith("_")
    ]
    assert violacoes == []


def test_service_do_dashboard_so_e_usado_pelo_router_do_dashboard():
    violacoes = [
        f"{arquivo} importa {modulo}"
        for pacote in ("api", "services", "rules", "notifications", "sync", "workers")
        for arquivo, modulo in _imports(pacote)
        if modulo.startswith("app.services.dashboard")
        and not arquivo.replace("\\", "/").endswith("api/v1/dashboard.py")
    ]
    assert violacoes == []
