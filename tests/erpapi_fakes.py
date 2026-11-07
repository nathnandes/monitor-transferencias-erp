import json
from collections.abc import Callable
from urllib.parse import parse_qs

import httpx2

from app.erp.config import ErpApiSettings

BASE_URL = "https://erpapi.teste.invalid"
TOKEN_PATH = "/teste/token"
ROTA = "/teste/servico-leitura"

USUARIO = "usuario-ficticio"
SENHA = "senha-ficticia-123"
CLIENT_ID = "cliente-ficticio"
CLIENT_SECRET = "segredo-ficticio-456"


def criar_settings(**sobrescrever) -> ErpApiSettings:
    valores = {
        "enabled": True,
        "base_url": BASE_URL,
        "token_path": TOKEN_PATH,
        "username": USUARIO,
        "password": SENHA,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "allowed_routes": ROTA,
        "timeout_seconds": 5,
        "token_renew_margin_seconds": 60,
        "token_ttl_fallback_seconds": 600,
    }
    valores.update(sobrescrever)
    return ErpApiSettings(_env_file=None, **valores)


class Relogio:
    def __init__(self, inicio: float = 1000.0) -> None:
        self.agora = inicio

    def __call__(self) -> float:
        return self.agora

    def avancar(self, segundos: float) -> None:
        self.agora += segundos


Resposta = httpx2.Response | Callable[[httpx2.Request], httpx2.Response] | Exception


def resposta_token(token: str, expires_in: int | None = 3600) -> httpx2.Response:
    corpo: dict = {"access_token": token, "token_type": "bearer"}
    if expires_in is not None:
        corpo["expires_in"] = expires_in
    return httpx2.Response(200, json=corpo)


def resposta_pagina(registros: list[dict], has_next, total=None) -> httpx2.Response:
    corpo = {"registros_teste": registros, "hasNext": has_next}
    if total is not None:
        corpo["Total"] = total
    return httpx2.Response(200, json=corpo)


class ServidorFalso:
    def __init__(self) -> None:
        self.filas: dict[str, list[Resposta]] = {}
        self.requisicoes: list[httpx2.Request] = []

    def enfileirar(self, rota: str, *respostas: Resposta) -> None:
        self.filas.setdefault(rota, []).extend(respostas)

    def chamadas(self, rota: str) -> list[httpx2.Request]:
        return [r for r in self.requisicoes if r.url.path == rota]

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._responder)

    def _responder(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        self.requisicoes.append(request)
        fila = self.filas.get(request.url.path)
        if not fila:
            raise AssertionError(f"requisicao inesperada: {request.method} {request.url.path}")
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)
        return item


def form(request: httpx2.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def corpo_json(request: httpx2.Request) -> dict:
    return json.loads(request.content)
