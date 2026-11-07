from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import AMBIENTES_LOCAIS


def _nomes(campo: str) -> AliasChoices:
    return AliasChoices(f"ERPAPI_{campo}", f"ERP_{campo}")


class ErpApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ERPAPI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,
    )

    enabled: bool = False

    base_url: str = Field(default="", validation_alias=_nomes("BASE_URL"))

    token_path: str = ""
    timeout_seconds: float = Field(default=30.0, gt=0)
    verify_ssl: bool = True

    permitir_http: bool = False

    app_env: str = Field(default="development", validation_alias=AliasChoices("APP_ENV"))

    username: str = Field(default="", validation_alias=_nomes("USERNAME"))
    password: SecretStr = Field(default=SecretStr(""), validation_alias=_nomes("PASSWORD"))
    client_id: str = Field(default="", validation_alias=_nomes("CLIENT_ID"))
    client_secret: SecretStr = Field(
        default=SecretStr(""), validation_alias=_nomes("CLIENT_SECRET")
    )

    ambiente: str = Field(default="producao", min_length=1, max_length=20)

    fuso: str = Field(default="America/Porto_Velho", min_length=1)

    campo_registros: str = Field(default="data", min_length=1)

    campo_total: str = Field(default="total", min_length=1)
    campo_tem_proxima: str = Field(default="hasNext", min_length=1)

    @property
    def producao(self) -> bool:
        return self.app_env.strip().lower() not in AMBIENTES_LOCAIS

    @field_validator("fuso")
    @classmethod
    def _fuso_valido(cls, valor: str) -> str:
        try:
            ZoneInfo(valor)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"fuso desconhecido: {valor}") from None
        return valor

    token_renew_margin_seconds: int = Field(default=300, ge=0)

    token_ttl_fallback_seconds: int = Field(default=3600, gt=0)

    allowed_routes: str = ""

    max_pages: int = Field(default=1000, gt=0)

    @property
    def rotas_permitidas(self) -> frozenset[str]:
        return frozenset(r.strip() for r in self.allowed_routes.split(",") if r.strip())

    def campos_obrigatorios_ausentes(self) -> list[str]:
        faltando = []
        for campo, valor in (
            ("ERPAPI_BASE_URL", self.base_url),
            ("ERPAPI_TOKEN_PATH", self.token_path),
            ("ERPAPI_USERNAME", self.username),
            ("ERPAPI_PASSWORD", self.password.get_secret_value()),
            ("ERPAPI_CLIENT_ID", self.client_id),
            ("ERPAPI_CLIENT_SECRET", self.client_secret.get_secret_value()),
        ):
            if not valor.strip():
                faltando.append(campo)
        return faltando


@lru_cache
def get_erpapi_settings() -> ErpApiSettings:
    return ErpApiSettings()
