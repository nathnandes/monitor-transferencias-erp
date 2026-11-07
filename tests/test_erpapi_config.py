import pytest

from app.erp.config import ErpApiSettings


def test_padroes_nao_apontam_para_servidor_nenhum():
    s = ErpApiSettings(_env_file=None)

    assert s.enabled is False
    assert s.base_url == ""
    assert s.token_path == ""
    assert s.username == ""
    assert s.client_id == ""
    assert s.rotas_permitidas == frozenset()
    assert s.verify_ssl is True

    assert "4664" not in repr(s)
    assert "localhost" not in repr(s)


def test_le_variaveis_erpapi_do_ambiente(monkeypatch):
    monkeypatch.setenv("ERPAPI_ENABLED", "true")
    monkeypatch.setenv("ERPAPI_BASE_URL", "https://erp.teste.invalid:9999")
    monkeypatch.setenv("ERPAPI_TOKEN_PATH", "/x/token")
    monkeypatch.setenv("ERPAPI_USERNAME", "u")
    monkeypatch.setenv("ERPAPI_PASSWORD", "p")
    monkeypatch.setenv("ERPAPI_CLIENT_ID", "cid")
    monkeypatch.setenv("ERPAPI_CLIENT_SECRET", "cs")
    monkeypatch.setenv("ERPAPI_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("ERPAPI_VERIFY_SSL", "false")
    monkeypatch.setenv("ERPAPI_ALLOWED_ROUTES", " /a , /b ,,")

    s = ErpApiSettings(_env_file=None)

    assert s.enabled is True
    assert s.base_url == "https://erp.teste.invalid:9999"
    assert s.token_path == "/x/token"
    assert s.timeout_seconds == 12.5
    assert s.verify_ssl is False
    assert s.password.get_secret_value() == "p"
    assert s.client_secret.get_secret_value() == "cs"
    assert s.rotas_permitidas == frozenset({"/a", "/b"})
    assert s.campos_obrigatorios_ausentes() == []


def test_lista_nomes_das_variaveis_ausentes_sem_valores():
    s = ErpApiSettings(_env_file=None, base_url="https://x.invalid", password="segredo-x")

    faltando = s.campos_obrigatorios_ausentes()

    assert faltando == [
        "ERPAPI_TOKEN_PATH",
        "ERPAPI_USERNAME",
        "ERPAPI_CLIENT_ID",
        "ERPAPI_CLIENT_SECRET",
    ]


def test_segredos_nao_aparecem_no_repr():
    s = ErpApiSettings(_env_file=None, password="senha-xyz", client_secret="segredo-xyz")

    assert "senha-xyz" not in repr(s)
    assert "segredo-xyz" not in repr(s)


@pytest.mark.parametrize("valor", ["0", "-1"])
def test_timeout_precisa_ser_positivo(valor, monkeypatch):
    monkeypatch.setenv("ERPAPI_TIMEOUT_SECONDS", valor)
    with pytest.raises(ValueError):
        ErpApiSettings(_env_file=None)
