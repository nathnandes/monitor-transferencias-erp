import ast
import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import httpx2
import pytest

from app.erp import ErpApiClient, ErpApiSettings, RequisicaoPaginada
from app.erp.errors import ErpApiDesabilitadoError
from tests.bloqueio_rede import TENTATIVAS, RedeBloqueadaError
from tests.erpapi_fakes import ROTA, TOKEN_PATH, criar_settings

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "conectar",
    [
        lambda: socket.create_connection(("erpapi.exemplo.invalid", 443), timeout=1),
        lambda: socket.getaddrinfo("erp.exemplo.invalid", 8080),
        lambda: socket.socket().connect(("203.0.113.10", 80)),
    ],
    ids=["create_connection", "dns", "connect"],
)
def test_guarda_da_suite_bloqueia_rede_externa(conectar):
    antes = len(TENTATIVAS)
    with pytest.raises(RedeBloqueadaError):
        conectar()
    assert len(TENTATIVAS) == antes + 1
    del TENTATIVAS[antes:]


def test_cliente_http_real_tambem_e_bloqueado():
    antes = len(TENTATIVAS)
    with httpx2.Client() as http, pytest.raises(RedeBloqueadaError):
        http.get("https://erpapi.exemplo.invalid/qualquer")
    assert len(TENTATIVAS) == antes + 1
    del TENTATIVAS[antes:]


def test_padrao_de_fabrica_e_desativado_e_vazio(monkeypatch):
    for nome in list(os.environ):
        if nome.upper().startswith("ERPAPI_"):
            monkeypatch.delenv(nome)
    s = ErpApiSettings(_env_file=None)
    assert s.enabled is False
    assert s.base_url == s.token_path == s.username == s.client_id == ""
    assert s.password.get_secret_value() == s.client_secret.get_secret_value() == ""
    assert s.rotas_permitidas == frozenset()


def test_desativado_bloqueia_tudo_mesmo_com_configuracao_completa():
    antes = len(TENTATIVAS)
    with ErpApiClient(criar_settings(enabled=False)) as client:
        with pytest.raises(ErpApiDesabilitadoError):
            client.autenticar()
        with pytest.raises(ErpApiDesabilitadoError):
            client.consultar(ROTA, RequisicaoPaginada())
        with pytest.raises(ErpApiDesabilitadoError):
            next(client.iterar_paginas(ROTA, campo_registros="x"))

        with pytest.raises(ErpApiDesabilitadoError):
            client._enviar(TOKEN_PATH, data={})
        with pytest.raises(ErpApiDesabilitadoError):
            client._http.post(ROTA)
    assert len(TENTATIVAS) == antes


def test_desativado_ignora_transporte_injetado():
    chamadas: list[httpx2.Request] = []

    def responder(request: httpx2.Request) -> httpx2.Response:
        chamadas.append(request)
        return httpx2.Response(200, json={})

    transporte = httpx2.MockTransport(responder)
    with ErpApiClient(criar_settings(enabled=False), transport=transporte) as client:
        with pytest.raises(ErpApiDesabilitadoError):
            client._http.post(ROTA)
    assert chamadas == []


def test_construir_o_client_nao_abre_conexao():
    antes = len(TENTATIVAS)
    ErpApiClient(criar_settings(enabled=True)).close()
    ErpApiClient(criar_settings(enabled=False)).close()
    assert len(TENTATIVAS) == antes


_MODULOS_DE_REDE = ("httpx", "httpx2", "requests", "urllib3", "aiohttp", "socket", "http.client")
_PROIBIDOS = (*_MODULOS_DE_REDE, "urllib.request", "app.erp")


_PERMITIDOS_POR_PACOTE = {"telegram": {"httpx2"}, "whatsapp": {"httpx2"}, "sync": {"app.erp"}}


def _arquivos_sem_rede() -> list[Path]:
    src = RAIZ / "src" / "app"
    connector = src / "erp"
    arquivos = sorted(p for p in src.rglob("*.py") if connector not in p.parents)
    arquivos += sorted((RAIZ / "migrations").rglob("*.py"))
    return arquivos


def test_varredura_cobre_todas_as_pastas_fora_do_connector():
    src = RAIZ / "src" / "app"
    cobertos = {p.relative_to(src).parts[0] for p in _arquivos_sem_rede() if src in p.parents}
    pacotes = {
        p.name
        for p in src.iterdir()
        if p.is_dir() and p.name != "erp" and (p / "__init__.py").exists()
    }
    assert pacotes <= cobertos, pacotes - cobertos


def _importados(caminho: Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
            nomes.update(f"{no.module}.{a.name}" for a in no.names)
    return nomes


@pytest.mark.parametrize(
    "arquivo", _arquivos_sem_rede(), ids=lambda p: p.relative_to(RAIZ).as_posix()
)
def test_api_seed_e_migrations_nao_importam_cliente_http_nem_connector(arquivo):
    src = RAIZ / "src" / "app"
    pacote = arquivo.relative_to(src).parts[0] if src in arquivo.parents else ""
    permitidos = _PERMITIDOS_POR_PACOTE.get(pacote, set())
    violacoes = {
        nome
        for nome in _importados(arquivo)
        for proibido in _PROIBIDOS
        if (nome == proibido or nome.startswith(proibido + ".")) and proibido not in permitidos
    }
    assert not violacoes, f"{arquivo.name} importa {sorted(violacoes)}"


_SCRIPT_PROCESSO_LIMPO = textwrap.dedent(
    """
    from bloqueio_rede import bloquear_rede_externa

    with bloquear_rede_externa() as tentativas:
        import app.erp
        import app.database.simulacao
        import app.main
        from app.erp import get_erpapi_settings
        from app.main import create_app
        from fastapi.testclient import TestClient

        assert get_erpapi_settings().enabled is False
        resposta = TestClient(create_app()).get("/health/live")
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["status"] == "ok"
    assert tentativas == [], tentativas
    print("processo-limpo-ok")
    """
)


def test_backend_importa_e_sobe_sem_variaveis_reais_nem_rede(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("ERPAPI_")}
    env["PYTHONPATH"] = os.pathsep.join([str(RAIZ / "src"), str(RAIZ / "tests")])
    resultado = subprocess.run(
        [sys.executable, "-c", _SCRIPT_PROCESSO_LIMPO],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert "processo-limpo-ok" in resultado.stdout


_SCRIPT_MIGRATIONS_OFFLINE = textwrap.dedent(
    """
    import sys
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from bloqueio_rede import bloquear_rede_externa

    raiz = Path(sys.argv[1])
    cfg = Config(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "migrations"))
    with bloquear_rede_externa() as tentativas:
        command.upgrade(cfg, "head", sql=True)  # modo offline: nao conecta
        assert "app.erp" not in sys.modules, "migrations carregaram o connector"
    assert tentativas == [], tentativas
    print("migrations-offline-ok")
    """
)


def test_migrations_rodam_offline_sem_erpapi_nem_rede(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("ERPAPI_")}
    env["PYTHONPATH"] = os.pathsep.join([str(RAIZ / "src"), str(RAIZ / "tests")])

    env["DATABASE_URL"] = "postgresql+psycopg://offline:offline@127.0.0.1:1/offline"
    resultado = subprocess.run(
        [sys.executable, "-c", _SCRIPT_MIGRATIONS_OFFLINE, str(RAIZ)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert "migrations-offline-ok" in resultado.stdout
    for tabela in ("empresas", "transferencias"):
        assert f"CREATE TABLE {tabela}" in resultado.stdout
