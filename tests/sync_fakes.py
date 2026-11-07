import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import httpx2
from sqlalchemy.orm import Session

from app.erp.client import ErpApiClient
from app.erp.servicos import (
    ROTA_CAD_LOJAS,
    ROTA_CAD_PRODUTOS,
    ROTA_PRECOS_CUSTOS,
    ROTA_SALDO_ESTOQUE_EMPRESA,
    ServicosErp,
)
from app.sync.comum import PoliticaRetry
from tests.erpapi_fakes import TOKEN_PATH, criar_settings

CAMPO_REGISTROS = "data"
TOKEN = "token-ficticio-sync-0001"


def saldo(
    empresa: str,
    produto: str,
    atual: str | float,
    disponivel: str | float,
    *,
    reservado: str | float | None = None,
    sub: str = "1",
    local: str = "1",
    lote: str | None = None,
    **extra,
) -> dict:
    registro = {
        "idempresa": int(empresa),
        "idproduto": int(produto),
        "idsubproduto": int(sub),
        "idlocalestoque": int(local),
        "descrlocalestoque": f"LOCAL {local}",
        "flaglote": "S" if lote else "N",
        "descrlote": lote,
        "flagestnegativo": "N",
        "qtdsaldoatual": atual,
        "qtdsaldoreserva": reservado,
        "qtdsaldodisponivel": disponivel,
        "dtalteracao": "2026-10-01 08:30:00",
        "flaginativo": "F",
    }
    registro.update(extra)
    return registro


def preco(
    empresa: str,
    produto: str,
    *,
    varejo: float | None = 10.5,
    custo: float | None = 6.25,
    sub: str = "1",
    dtalteracao: str = "2026-10-01 08:30:00",
    **extra,
) -> dict:
    registro = {
        "idempresa": int(empresa),
        "idproduto": int(produto),
        "idsubproduto": int(sub),
        "valprecovarejo": varejo,
        "valpromvarejo": 0.0,
        "valprecoatacado": 0.0,
        "valpromatacado": 0.0,
        "valcustorepos": custo,
        "custogerencial": custo,
        "custonotafiscal": custo,
        "qtdmultiplicador": 1.0,
        "dtalteracao": dtalteracao,
        "dtalteracaovar": dtalteracao,
        "flaginativo": "F",
    }
    registro.update(extra)
    return registro


def produto(
    id_produto: str,
    nome: str = "PRODUTO FICTICIO",
    *,
    sub: str | None = None,
    dtalteracao: str = "2026-10-01 08:30:00",
    **extra,
) -> dict:
    registro = {
        "idproduto": int(id_produto),
        "idsubproduto": int(sub or id_produto),
        "descrcomproduto": nome,
        "descrresproduto": nome[:40],
        "descrsecao": "SECAO FICTICIA",
        "embalagemsaida": "UN",
        "flaginativo": "F",
        "flagbloqueiavenda": "F",
        "dtalteracao": dtalteracao,
    }
    registro.update(extra)
    return registro


def loja(id_erp: str, nome: str, bairro: str | None = "Bairro Ficticio") -> dict:
    return {"idempresa": int(id_erp), "nomefantasia": nome, "bairro": bairro}


def pagina_json(registros: list[dict], tem_proxima: bool) -> httpx2.Response:
    return httpx2.Response(
        200, json={CAMPO_REGISTROS: registros, "hasNext": tem_proxima, "total": len(registros)}
    )


class ErpApiSimulado:
    def __init__(self) -> None:
        self.lojas: list[dict] = []

        self.estoque: dict[str, list[list[dict]]] = {}
        self.precos: dict[str, list[list[dict]]] = {}
        self.produtos: list[list[dict]] = []

        self.falhas: dict[tuple[str, int], list[httpx2.Response | Exception]] = {}
        self.falhas_token: list[httpx2.Response] = []
        self.requisicoes: list[httpx2.Request] = []

    def com_estoque(self, empresa: str, *paginas: list[dict]) -> "ErpApiSimulado":
        self.estoque[empresa] = list(paginas)
        return self

    def com_precos(self, empresa: str, *paginas: list[dict]) -> "ErpApiSimulado":
        self.precos[empresa] = list(paginas)
        return self

    def com_produtos(self, *paginas: list[dict]) -> "ErpApiSimulado":
        self.produtos = list(paginas)
        return self

    def consultas(self, rota: str) -> list[tuple[int, tuple[tuple[str, str, str], ...]]]:
        feitas = []
        for r in self.requisicoes:
            if r.url.path == rota:
                corpo = json.loads(r.content)
                filtros = tuple((c["campo"], c["operador"], c["valor"]) for c in corpo["clausulas"])
                feitas.append((corpo["page"], filtros))
        return feitas

    def falhar(self, empresa: str, pagina: int, *respostas) -> "ErpApiSimulado":
        self.falhas.setdefault((empresa, pagina), []).extend(respostas)
        return self

    def chamadas_estoque(self, empresa: str | None = None) -> list[tuple[str, int]]:
        return [(e, p) for e, p, _ in self.consultas_estoque(empresa)]

    def consultas_estoque(
        self, empresa: str | None = None
    ) -> list[tuple[str, int, tuple[tuple[str, str, str], ...]]]:
        feitas = []
        for r in self.requisicoes:
            if r.url.path == ROTA_SALDO_ESTOQUE_EMPRESA:
                corpo = json.loads(r.content)
                id_empresa = corpo["clausulas"][0]["valor"]
                filtros = tuple(
                    (c["campo"], c["operador"], c["valor"]) for c in corpo["clausulas"][1:]
                )
                if empresa is None or id_empresa == empresa:
                    feitas.append((id_empresa, corpo["page"], filtros))
        return feitas

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._responder)

    def _responder(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        self.requisicoes.append(request)
        caminho = request.url.path
        if caminho == TOKEN_PATH:
            if self.falhas_token:
                return self.falhas_token.pop(0)
            return httpx2.Response(200, json={"access_token": TOKEN, "expires_in": 3600})

        corpo = json.loads(request.content)
        pagina = corpo["page"]
        if caminho == ROTA_CAD_LOJAS:
            return pagina_json(self.lojas if pagina == 1 else [], False)
        if caminho == ROTA_CAD_PRODUTOS:
            assert all(c["campo"] != "idempresa" for c in corpo["clausulas"])
            fila = self.falhas.get(("produtos", pagina))
            if fila:
                item = fila.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            return _paginar(self.produtos or [[]], pagina, corpo["clausulas"])
        if caminho in (ROTA_SALDO_ESTOQUE_EMPRESA, ROTA_PRECOS_CUSTOS):
            clausula = corpo["clausulas"][0]
            assert clausula == {
                "campo": "idempresa",
                "valor": clausula["valor"],
                "operadorLogico": "AND",
                "operador": "IGUAL",
            }
            empresa = clausula["valor"]
            fila = self.falhas.get((empresa, pagina))
            if fila:
                item = fila.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item
            dados = self.estoque if caminho == ROTA_SALDO_ESTOQUE_EMPRESA else self.precos
            return _paginar(dados.get(empresa, [[]]), pagina, corpo["clausulas"][1:])
        raise AssertionError(f"rota inesperada: {caminho}")


def _paginar(paginas: list[list[dict]], pagina: int, filtros: list[dict]) -> httpx2.Response:
    if filtros:
        todos = [r for p in paginas for r in p if _atende(r, filtros)]
        inicio = (pagina - 1) * 100
        return pagina_json(todos[inicio : inicio + 100], inicio + 100 < len(todos))
    registros = paginas[pagina - 1] if pagina <= len(paginas) else []
    return pagina_json(registros, pagina < len(paginas))


def _atende(registro: dict, filtros: list[dict]) -> bool:
    for f in filtros:
        valor = registro.get(f["campo"])
        if f["operador"] == "IGUAL":
            if str(valor) != f["valor"]:
                return False
        elif f["operador"] == "MAIOR":
            if valor is None or float(valor) <= float(f["valor"]):
                return False
        elif f["operador"] == "MAIOR_IGUAL" and f["campo"] == "dtalteracao":
            if valor is None or datetime.fromisoformat(str(valor)) < datetime.fromisoformat(
                f["valor"]
            ):
                return False
        else:
            raise AssertionError(f"filtro nao simulado: {f}")
    return True


def servicos_para(simulado: ErpApiSimulado, **sobrescrever) -> ServicosErp:
    valores = {
        "allowed_routes": ",".join(
            (ROTA_CAD_LOJAS, ROTA_SALDO_ESTOQUE_EMPRESA, ROTA_PRECOS_CUSTOS, ROTA_CAD_PRODUTOS)
        ),
        "campo_registros": CAMPO_REGISTROS,
        **sobrescrever,
    }
    settings = criar_settings(**valores)
    return ServicosErp(
        ErpApiClient(settings, transport=simulado.transport()),
        campo_registros=settings.campo_registros,
        max_paginas=settings.max_pages,
    )


class Dormir:
    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


def politica(tentativas: int = 3) -> tuple[PoliticaRetry, Dormir]:
    dormir = Dormir()
    return PoliticaRetry(tentativas=tentativas, espera_segundos=2.0, dormir=dormir), dormir


def fabrica_de(db: Session) -> Callable[[], Session]:
    conexao = db.connection()
    return lambda: Session(bind=conexao, join_transaction_mode="create_savepoint")


def dec(valor: str) -> Decimal:
    return Decimal(valor)
