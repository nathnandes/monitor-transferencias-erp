import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (RAIZ / ".git").exists(), reason="git indisponivel"
)

VARIAVEIS_ERPAPI = (
    "ERPAPI_BASE_URL",
    "ERPAPI_TOKEN_PATH",
    "ERPAPI_USERNAME",
    "ERPAPI_PASSWORD",
    "ERPAPI_CLIENT_ID",
    "ERPAPI_CLIENT_SECRET",
    "ERPAPI_TIMEOUT_SECONDS",
    "ERPAPI_VERIFY_SSL",
    "ERPAPI_ENABLED",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, timeout=60)


def _versionados() -> list[str]:

    return _git("ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout.split("\0")


@pytest.mark.parametrize(
    "caminho",
    [
        ".env",
        ".env.local",
        ".env.homologacao",
        "frontend/.env",
        ".venv/pyvenv.cfg",
        "tests/fixtures/erpapi/servico.raw.json",
        "tests/fixtures/erpapi/real/resposta.json",
        "docs/erpapi/amostras/servico.raw",
        "docs/postman/erpapi.postman_environment.json",
        "credenciais/erpapi.txt",
        "notas.local",
        "certificado.pem",
        "node_modules/pacote/index.js",
        "frontend/node_modules/pacote/index.js",
        "logs/api.txt",
        "uvicorn.log",
        "frontend/npm-debug.log",
        "erpapi.token",
        "token.json",
        "docs/erpapi/amostras/token.txt",
        "tokens/homologacao.txt",
        "acesso.token.json",
    ],
)
def test_arquivos_sensiveis_sao_ignorados_pelo_git(caminho):
    assert _git("check-ignore", "-q", "--no-index", caminho).returncode == 0, (
        f"{caminho} nao esta no .gitignore"
    )


def test_env_example_continua_versionado():
    assert _git("check-ignore", "-q", "--no-index", ".env.example").returncode == 1


def test_nenhum_arquivo_sensivel_versionado():
    proibidos = re.compile(r"(^|/)(\.env(\..+)?|.+\.(pem|key|pfx|p12|raw|raw\.json))$")
    suspeitos = [
        f for f in _versionados() if f and proibidos.search(f) and not f.endswith(".env.example")
    ]
    assert suspeitos == []


def _env_example() -> dict[str, str]:
    valores = {}
    for linha in (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if "=" in linha:
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip()
    return valores


def test_env_example_declara_erpapi_desativado_e_sem_valores_reais():
    env = _env_example()
    for nome in VARIAVEIS_ERPAPI:
        assert nome in env, f"{nome} ausente do .env.example"
    assert env["ERPAPI_ENABLED"] == "false"

    assert env["ERPAPI_TOKEN_PATH"] == "/erpcore-auth/oauth/token"

    for nome in (
        "ERPAPI_BASE_URL",
        "ERPAPI_USERNAME",
        "ERPAPI_PASSWORD",
        "ERPAPI_CLIENT_ID",
        "ERPAPI_CLIENT_SECRET",
        "ERPAPI_ALLOWED_ROUTES",
    ):
        assert env[nome] == "", f"{nome} deve ficar vazio no .env.example"
    assert env["ERPAPI_VERIFY_SSL"] == "true"
    assert float(env["ERPAPI_TIMEOUT_SECONDS"]) > 0


_PADROES_SEGREDO = {
    "JWT": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "Bearer com valor": re.compile(r"Bearer\s+(?!<)[A-Za-z0-9._~+/=-]{16,}"),
    "chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "segredo ERPAPI preenchido": re.compile(
        r"ERPAPI_(PASSWORD|CLIENT_SECRET|USERNAME|CLIENT_ID|BASE_URL)[ \t]*=[ \t]*[^\s#<{]+"
    ),
    "IPv4 fora de loopback e 0.0.0.0": re.compile(
        r"\b(?!127\.)(?!0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b"
    ),
}

_EXTENSOES_TEXTO = (".md", ".py", ".toml", ".ini", ".yml", ".yaml", ".example", ".json", ".txt")


def _arquivos_texto_versionados() -> list[Path]:
    arquivos = []
    for f in _versionados():
        if not f or f.startswith(("frontend/", "tests/")) or f.endswith("package-lock.json"):
            continue
        if f.endswith(_EXTENSOES_TEXTO) or f in {".gitignore", "Dockerfile"}:
            arquivos.append(RAIZ / f)
    return arquivos


def test_arquivos_versionados_nao_contem_segredos():
    achados = []
    for arquivo in _arquivos_texto_versionados():
        if not arquivo.exists():
            continue
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        for nome, padrao in _PADROES_SEGREDO.items():
            for m in padrao.finditer(texto):
                achados.append(f"{arquivo.relative_to(RAIZ).as_posix()}: {nome}: {m.group(0)[:40]}")
    assert achados == [], "\n".join(achados)


def test_frontend_nao_conhece_o_erpapi():
    referencias = []
    for arquivo in (RAIZ / "frontend" / "src").rglob("*"):
        if arquivo.suffix in {".ts", ".tsx", ".css"}:
            texto = arquivo.read_text(encoding="utf-8").lower()
            for termo in ("erpapi", "erpcore", "oauth/token", "client_secret"):
                if termo in texto:
                    referencias.append(f"{arquivo.name}: {termo}")
    assert referencias == []
