import re

MASCARA = "***"

_CHAVES = (
    "password_hash",
    "password",
    "passwd",
    "senha",
    "client_secret",
    "secret",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "api_key",
    "apikey",
)


_POR_CHAVE = re.compile(
    r"(?P<prefixo>(?<![A-Za-z0-9_])[\"']?(?:" + "|".join(_CHAVES) + r")[\"']?\s*[:=]\s*)"
    r"(?P<aspas>[\"']?)(?P<valor>[^\"'\s,;&}\]]+)",
    re.IGNORECASE,
)


_AUTHORIZATION = re.compile(
    r"(?P<prefixo>(?<![A-Za-z0-9_])[\"']?authorization[\"']?\s*[:=]\s*[\"']?"
    r"(?:(?:bearer|basic|token)\s+)?)(?P<valor>[^\"'\s,;&}\]]+)",
    re.IGNORECASE,
)


_BEARER = re.compile(r"(?P<prefixo>\bbearer\s+)(?P<valor>[A-Za-z0-9._~+/=-]{8,})", re.IGNORECASE)


_URL_COM_SENHA = re.compile(
    r"(?P<prefixo>[A-Za-z][A-Za-z0-9+.-]*://[^:/\s@]+:)(?P<valor>[^@\s/]+)(?=@)"
)


_ARGON2 = re.compile(r"\$argon2(?:id|i|d)\$[A-Za-z0-9+/=$,.-]+")


_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")


_TOKEN_TELEGRAM = re.compile(r"(?:(?<=bot)|(?<![A-Za-z0-9]))\d{6,12}:[A-Za-z0-9_-]{30,}")


_TOKEN_META = re.compile(r"(?<![A-Za-z0-9])EAA[A-Za-z0-9]{30,}")


def mascarar_texto(texto: str) -> str:
    if not texto:
        return texto
    texto = _ARGON2.sub(MASCARA, texto)
    texto = _JWT.sub(MASCARA, texto)
    texto = _TOKEN_TELEGRAM.sub(MASCARA, texto)
    texto = _TOKEN_META.sub(MASCARA, texto)
    texto = _AUTHORIZATION.sub(lambda m: m.group("prefixo") + MASCARA, texto)
    texto = _BEARER.sub(lambda m: m.group("prefixo") + MASCARA, texto)
    texto = _POR_CHAVE.sub(lambda m: m.group("prefixo") + m.group("aspas") + MASCARA, texto)
    texto = _URL_COM_SENHA.sub(lambda m: m.group("prefixo") + MASCARA, texto)
    return texto
