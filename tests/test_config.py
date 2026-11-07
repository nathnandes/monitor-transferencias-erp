import pytest

from app.core.config import Settings, get_settings


def test_monta_url_a_partir_das_partes():
    settings = Settings(
        _env_file=None,
        database_url="",
        postgres_user="erp",
        postgres_password="senha",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="erp_automation",
    )

    assert settings.sqlalchemy_url == ("postgresql+psycopg://erp:senha@db:5432/erp_automation")


def test_database_url_tem_precedencia_sobre_as_partes():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://outro:x@outrohost:5433/outrobanco",
        postgres_user="erp",
        postgres_password="senha",
        postgres_host="db",
    )

    assert settings.sqlalchemy_url.endswith("@outrohost:5433/outrobanco")


def test_senha_com_caractere_especial_e_escapada():
    settings = Settings(
        _env_file=None,
        database_url="",
        postgres_user="erp",
        postgres_password="p@ss/word",
        postgres_host="db",
        postgres_port=5432,
        postgres_db="erp_automation",
    )

    assert "p%40ss%2Fword" in settings.sqlalchemy_url

    assert settings.sqlalchemy_url.count("@") == 1


def test_segredos_nao_vazam_no_repr():
    settings = Settings(
        _env_file=None,
        postgres_password="senha-secreta",
        telegram_bot_token="token-telegram",
    )

    texto = repr(settings)
    assert "senha-secreta" not in texto
    assert "token-telegram" not in texto


def test_is_production_reconhece_os_dois_idiomas():
    assert Settings(_env_file=None, app_env="producao").is_production
    assert Settings(_env_file=None, app_env="production").is_production
    assert not Settings(_env_file=None, app_env="development").is_production


def test_get_settings_retorna_a_mesma_instancia():
    assert get_settings() is get_settings()


@pytest.mark.parametrize("app_env", ["homologacao", "prodcao", "staging", ""])
def test_ambiente_que_nao_e_local_conta_como_producao(app_env):
    assert Settings(_env_file=None, app_env=app_env).is_production


@pytest.mark.parametrize("app_env", ["development", "Development", "dev", "local", "test"])
def test_so_os_ambientes_locais_nao_sao_producao(app_env):
    assert not Settings(_env_file=None, app_env=app_env).is_production
