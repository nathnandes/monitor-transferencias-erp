from datetime import date
from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AMBIENTES_LOCAIS = frozenset({"development", "dev", "local", "test"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"

    environment: str = ""
    app_name: str = "erp-automation"
    log_level: str = "INFO"

    log_format: Literal["texto", "json"] = "texto"
    tz: str = "America/Porto_Velho"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: str = ""

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "erp_automation"
    postgres_user: str = ""
    postgres_password: SecretStr = SecretStr("")

    db_connect_timeout_seconds: int = 5

    jwt_secret: SecretStr = SecretStr("")
    jwt_access_token_expire_minutes: int = Field(30, ge=1, le=1440)
    auth_login_rate_limit: int = Field(5, ge=1)
    auth_login_rate_window_seconds: int = Field(900, ge=1)

    auth_login_ip_rate_limit: int = Field(20, ge=1)

    auth_sessao_continua_max_horas: int = Field(168, ge=1)

    telegram_enabled: bool = False
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    telegram_timeout_seconds: float = Field(10.0, gt=0, le=60)

    whatsapp_enabled: bool = False

    whatsapp_provedor: Literal["meta", "baileys"] = "meta"
    whatsapp_gateway_url: str = "http://127.0.0.1:3100"

    whatsapp_gateway_token: SecretStr = SecretStr("")

    whatsapp_access_token: SecretStr = SecretStr("")

    whatsapp_phone_number_id: str = ""
    whatsapp_api_version: str = Field("v21.0", pattern=r"^v\d+\.\d+$")

    whatsapp_template: str = ""
    whatsapp_template_idioma: str = "pt_BR"
    whatsapp_timeout_seconds: float = Field(10.0, gt=0, le=60)

    monitor_interval_seconds: int = Field(60, ge=10, le=3600)

    alerta_sincronizacao_parada_minutos: int = Field(30, ge=5, le=1440)

    resumo_diario_horario: str = Field("07:00", pattern=r"^$|^([01]\d|2[0-3]):[0-5]\d$")

    sync_empresas: str = "1,2,3,4,5,6"

    estoque_locais_perda: str = "6:40=Avaria"

    estoque_locais_somados: str = "1:1=8+9"

    estoque_locais_fora_da_loja: str = (
        "TROCAS E DEVOLUCOES,APURACAO,AVARIAS,LABORATORIO,PISO,OUTROLOCAL,DEPOSITO TRANSIT"
    )

    estoque_depositos_abastecimento: str = "4,5"

    sync_estoque_intervalo_segundos: int = Field(300, ge=0)

    sync_estoque_completo_horario: str = Field("02:00", pattern=r"^$|^([01]\d|2[0-3]):[0-5]\d$")
    sync_empresas_intervalo_segundos: int = Field(86400, ge=0)

    sync_transferencias_intervalo_segundos: int = Field(300, ge=0)
    sync_transferencias_janela_dias: int = Field(3, ge=1, le=60)

    sync_precos_intervalo_segundos: int = Field(300, ge=0)
    sync_precos_completo_horario: str = Field("03:30", pattern=r"^$|^([01]\d|2[0-3]):[0-5]\d$")

    sync_vendas_intervalo_segundos: int = Field(300, ge=0)
    sync_vendas_janela_dias: int = Field(3, ge=1, le=60)
    sync_vendas_historico_dias: int = Field(400, ge=1, le=2000)
    sync_vendas_dias_por_ciclo: int = Field(30, ge=0, le=400)

    sync_movimentos_intervalo_segundos: int = Field(600, ge=0)
    sync_movimentos_janela_dias: int = Field(3, ge=1, le=60)
    sync_movimentos_historico_dias: int = Field(400, ge=1, le=2000)
    sync_movimentos_dias_por_ciclo: int = Field(5, ge=0, le=400)

    justificar_avulsas_desde: date | None = None

    sync_retry_tentativas: int = Field(3, ge=1, le=10)
    sync_retry_espera_segundos: float = Field(2.0, ge=0, le=300)

    sync_verificacao_segundos: int = Field(5, ge=1, le=300)

    anomalias_intervalo_segundos: int = Field(3600, ge=60, le=604800)

    anomalias_janela_avaliacao_dias: int = Field(7, ge=1, le=90)
    anomalias_historico_dias: int = Field(365, ge=30, le=1825)

    anomalias_minimo_treino: int = Field(500, ge=50, le=100000)

    anomalias_fracao_alerta: float = Field(0.02, gt=0, lt=0.5)

    @property
    def empresas_sincronizadas(self) -> tuple[str, ...]:
        vistos: dict[str, None] = {}
        for parte in self.sync_empresas.split(","):
            if parte.strip():
                vistos[parte.strip()] = None
        return tuple(vistos)

    @property
    def locais_perda(self) -> tuple[tuple[str, str, str], ...]:
        locais: dict[tuple[str, str], str] = {}
        for parte in self.estoque_locais_perda.split(","):
            chave, _, motivo = parte.partition("=")
            empresa, _, local = chave.partition(":")
            if empresa.strip() and local.strip():
                locais[(empresa.strip(), local.strip())] = motivo.strip() or "Perda"
        return tuple((e, loc, m) for (e, loc), m in locais.items())

    @property
    def depositos_abastecimento(self) -> tuple[str, ...]:
        codigos = (c.strip() for c in self.estoque_depositos_abastecimento.split(","))
        return tuple(dict.fromkeys(c for c in codigos if c))

    @property
    def locais_fora_da_loja(self) -> tuple[str, ...]:
        return tuple(
            p.strip().upper() for p in self.estoque_locais_fora_da_loja.split(",") if p.strip()
        )

    @property
    def locais_somados(self) -> dict[tuple[str, str], str]:
        destino: dict[tuple[str, str], str] = {}
        for parte in self.estoque_locais_somados.split(","):
            chave, _, outros = parte.partition("=")
            empresa, _, local = chave.partition(":")
            if not (empresa.strip() and local.strip()):
                continue
            for outro in outros.split("+"):
                if outro.strip() and outro.strip() != local.strip():
                    destino[(empresa.strip(), outro.strip())] = local.strip()
        return destino

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url

        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() not in AMBIENTES_LOCAIS


@lru_cache
def get_settings() -> Settings:
    return Settings()
