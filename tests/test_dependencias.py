import re
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _ler(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="utf-8")


def _nome(requisito: str) -> str:
    return re.split(r"[\[<>=!~;\s]", requisito, maxsplit=1)[0].lower().replace("_", "-")


def _fixadas() -> dict[str, str]:
    fixadas = {}
    for linha in _ler("constraints.txt").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if linha:
            nome, versao = linha.split("==")
            fixadas[nome.lower().replace("_", "-")] = versao
    return fixadas


def test_toda_dependencia_do_pyproject_tem_versao_fixa():
    projeto = tomllib.loads(_ler("pyproject.toml"))["project"]
    diretas = projeto["dependencies"] + projeto["optional-dependencies"]["dev"]
    fixadas = _fixadas()
    faltando = sorted({_nome(r) for r in diretas} - set(fixadas))
    assert faltando == []


def test_build_e_ci_instalam_com_as_versoes_fixas():
    dockerfile = _ler("Dockerfile")
    assert dockerfile.count("-c constraints.txt") >= 2
    assert "pip install -c constraints.txt" in _ler(".github/workflows/ci.yml")


def test_ci_audita_as_dependencias():
    ci = _ler(".github/workflows/ci.yml")
    assert "pip-audit -r constraints.txt" in ci
    assert "npm audit" in ci


def test_ci_e_pre_commit_conferem_a_formatacao():
    assert "ruff format --check" in _ler(".github/workflows/ci.yml")
    assert "id: ruff-format" in _ler(".pre-commit-config.yaml")
