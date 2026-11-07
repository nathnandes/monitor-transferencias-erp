import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import func, select

from app.database.models import Empresa, IntegracaoErro, Sincronizacao, Transferencia
from app.erp.client import ErpApiClient
from app.erp.servicos import (
    ROTA_CAD_LOJAS,
    ROTA_ITENS_ENTRADA,
    ROTA_ITENS_SAIDA,
    ROTA_NOTAS_ENTRADA,
    ROTA_NOTAS_SAIDA,
    ServicosErp,
)
from app.rules.regras import transferencia_coi_errado
from app.sync.empresas import sincronizar_empresas
from app.sync.transferencias import sincronizar_transferencias
from tests.erpapi_fakes import TOKEN_PATH, criar_settings
from tests.sync_fakes import fabrica_de, pagina_json, politica

pytestmark = pytest.mark.integration

AMBIENTE = "teste-sync"
EMPRESAS = ("1", "2", "3", "4", "5", "6")
AGORA = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
ONTEM = "2026-10-07 10:00:00"
ROTAS = (ROTA_CAD_LOJAS, ROTA_ITENS_SAIDA, ROTA_NOTAS_SAIDA, ROTA_ITENS_ENTRADA, ROTA_NOTAS_ENTRADA)


@pytest.fixture(autouse=True)
def _sem_dados_reais(db_vazio):
    pass


def cnpj(empresa: str) -> str:
    return f"9999000000{int(empresa):04d}"


def chave(n: int) -> str:
    return f"{n:044d}"


class NotasSimuladas:
    def __init__(self) -> None:
        self.lojas = [
            {"idempresa": int(e), "nomefantasia": f"Loja {e}", "cnpj": cnpj(e)} for e in EMPRESAS
        ]
        self.itens: dict[str, list[dict]] = {ROTA_ITENS_SAIDA: [], ROTA_ITENS_ENTRADA: []}
        self.notas: dict[str, list[dict]] = {ROTA_NOTAS_SAIDA: [], ROTA_NOTAS_ENTRADA: []}
        self.rotas: list[str] = []
        self.consultas: list[tuple[str, tuple]] = []

    def saida(self, empresa, planilha, coi, para_cnpj, n_chave, *, cancelada=False, data=ONTEM):
        self._nota(ROTA_NOTAS_SAIDA, empresa, planilha, para_cnpj, n_chave, data, cancelada, True)
        self._item(ROTA_ITENS_SAIDA, empresa, planilha, coi, data)
        return self

    def entrada(self, empresa, planilha, coi, de_cnpj, n_chave, *, data=ONTEM):
        self._nota(ROTA_NOTAS_ENTRADA, empresa, planilha, de_cnpj, n_chave, data, False, False)
        self._item(ROTA_ITENS_ENTRADA, empresa, planilha, coi, data)
        return self

    def _nota(self, rota, empresa, planilha, outra_parte, n_chave, data, cancelada, saida):
        nota = {
            "idempresa": int(empresa),
            "idplanilha": planilha,
            "numnota": planilha + 1000,
            "serienota": "1",
            "cnpjcpf": outra_parte,
            "dtemissao": data[:10],
            "dtmovimento": data,
            "dtalteracao": data,
            "tipocategoria": "F",
            "tipoitemcategoria": "F1",
            "valcontabil": 1234.56,
        }
        if saida:
            nota |= {
                "chave": chave(n_chave),
                "flagnotacancel": "T" if cancelada else "F",
                "nomeusuario": "EMISSOR FICTICIO",
            }
        else:
            nota |= {"chavenfe": chave(n_chave), "notacancelada": "T" if cancelada else "F"}
        self.notas[rota].append(nota)

    def _item(self, rota, empresa, planilha, coi, data, produtos=(910001, 910002)):
        saida = rota == ROTA_ITENS_SAIDA
        for seq, produto in enumerate(produtos, start=1):
            self.itens[rota].append(
                {
                    "idempresa": int(empresa),
                    "idplanilha": planilha,
                    "idoperacao": coi,
                    "idproduto": produto,
                    "idsubproduto": produto,
                    "numsequencia": seq,
                    "qtdproduto": 2.5 * seq,
                    "descrproduto": f"PRODUTO FICTICIO {produto}",
                    "dtmovimento": data[:10],
                    "valtotliquido": 10.0 * seq,
                    "cfop": "5152" if saida else "1152",
                }
            )

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._responder)

    def _responder(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        caminho = request.url.path
        if caminho == TOKEN_PATH:
            return httpx2.Response(200, json={"access_token": "tk-ficticio", "expires_in": 3600})
        self.rotas.append(caminho)
        corpo = json.loads(request.content)
        clausulas = tuple((c["campo"], c["operador"], c["valor"]) for c in corpo["clausulas"])
        self.consultas.append((caminho, clausulas))
        if caminho == ROTA_CAD_LOJAS:
            return pagina_json(self.lojas if corpo["page"] == 1 else [], False)
        base = self.itens[caminho] if caminho in self.itens else self.notas.get(caminho)
        if base is None:
            raise AssertionError(f"rota inesperada: {caminho}")
        registros = [r for r in base if _atende(r, corpo["clausulas"])]
        return pagina_json(registros if corpo["page"] == 1 else [], False)


def _atende(registro: dict, clausulas: list[dict]) -> bool:
    for c in clausulas:
        valor = registro.get(c["campo"])
        if c["operador"] == "IGUAL":
            texto = str(valor)[:10] if c["campo"] == "dtmovimento" else str(valor)
            if texto != c["valor"]:
                return False
        else:
            raise AssertionError(f"filtro nao simulado: {c}")
    return True


def _servicos(simulado: NotasSimuladas) -> ServicosErp:
    settings = criar_settings(allowed_routes=",".join(ROTAS), campo_registros="data")
    return ServicosErp(
        ErpApiClient(settings, transport=simulado.transport()),
        campo_registros="data",
        max_paginas=settings.max_pages,
    )


def _sincronizar(db, simulado):
    sincronizar_empresas(
        fabrica_de(db),
        _servicos(simulado),
        ambiente=AMBIENTE,
        empresas_ativas=EMPRESAS,
        politica=politica()[0],
    )
    return sincronizar_transferencias(
        fabrica_de(db),
        _servicos(simulado),
        ambiente=AMBIENTE,
        empresas=EMPRESAS,
        politica=politica()[0],
        janela=timedelta(days=3),
        agora=lambda: AGORA,
    )


def _por_chave(db) -> dict[int, Transferencia]:
    db.expire_all()
    return {int(t.chave_nfe): t for t in db.scalars(select(Transferencia))}


def _codigo(db, empresa_id: int | None) -> str | None:
    return db.get(Empresa, empresa_id).id_erp if empresa_id else None


@pytest.fixture
def simulado() -> NotasSimuladas:
    return (
        NotasSimuladas()
        .saida("1", 101, 8040, cnpj("3"), 1)
        .entrada("3", 301, 7161, cnpj("1"), 1)
        .saida("2", 201, 8051, cnpj("3"), 2, data="2026-10-06 10:00:00")
        .saida("6", 601, 8061, cnpj("1"), 3)
        .entrada("1", 111, 7661, cnpj("6"), 3)
        .saida("4", 401, 8039, cnpj("5"), 4)
        .entrada("5", 501, 7163, cnpj("4"), 4)
        .saida("5", 551, 8052, cnpj("2"), 5, cancelada=True)
        .saida("3", 351, 8051, "12345678000199", 6)
        .entrada("2", 251, 7162, cnpj("4"), 99)
        .saida("1", 102, 8040, cnpj("2"), 7, data="2026-09-01 10:00:00")
    )


def test_grava_uma_transferencia_por_nota_de_saida_e_completa_com_a_entrada(db, simulado):
    _sincronizar(db, simulado)
    t = _por_chave(db)

    assert sorted(t) == [1, 2, 3, 4, 5, 6]
    certa = t[1]
    assert (certa.id_erp, certa.numero_nota, certa.coi, certa.coi_entrada) == (
        "101",
        "1101",
        "8040",
        "7161",
    )
    assert (_codigo(db, certa.empresa_origem_id), _codigo(db, certa.empresa_destino_id)) == (
        "1",
        "3",
    )
    assert _codigo(db, certa.empresa_entrada_id) == "3"
    assert certa.status == "PROCESSADA"
    assert certa.problemas_coi == []
    assert certa.data_criacao and certa.data_processamento
    assert certa.quantidade_itens == len(certa.itens) == 2
    assert [i.quantidade_processada for i in certa.itens] == [
        i.quantidade_solicitada for i in certa.itens
    ]


def test_coi_fora_do_padrao_e_outro_tipo_e_nao_erro(db, simulado):
    _sincronizar(db, simulado)
    t = _por_chave(db)

    assert all(x.problemas_coi == [] for x in t.values())

    assert all(t[n].entre_empresas for n in (1, 3, 5))
    assert (t[3].status, t[3].coi_entrada) == ("PROCESSADA", "7661")

    assert t[2].status == "PENDENTE"
    assert not any(t[n].entre_empresas for n in (2, 4, 6))
    assert t[6].empresa_destino_id is None


def test_alerta_de_coi_errado_so_para_nota_sem_coi(db, simulado):

    simulado.entrada("3", 302, None, cnpj("2"), 2, data="2026-10-06 15:00:00")

    _sincronizar(db, simulado)
    t = _por_chave(db)

    assert t[2].problemas_coi == ["nota de entrada sem COI"]
    assert t[2].entre_empresas
    ocorrencias = transferencia_coi_errado(db, AGORA)
    assert {o.transferencia_id for o in ocorrencias} == {t[2].id}


def test_execucao_sem_problema_de_leitura_e_sucesso(db, simulado):
    resultado = _sincronizar(db, simulado)

    assert resultado.status == "sucesso", resultado.mensagem
    assert db.scalars(select(IntegracaoErro)).all() == []


def _por_dia(consultas):
    return [c for c in consultas if "dtmovimento" in [campo for campo, _, _ in c]]


def test_consulta_os_itens_um_dia_por_vez_com_filtros_simples(db, simulado):
    _sincronizar(db, simulado)

    itens_saida = _por_dia(cl for rota, cl in simulado.consultas if rota == ROTA_ITENS_SAIDA)
    itens_entrada = _por_dia(cl for rota, cl in simulado.consultas if rota == ROTA_ITENS_ENTRADA)
    dias = {dict((campo, valor) for campo, _, valor in cl)["dtmovimento"] for cl in itens_saida}
    assert dias == {"2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"}
    assert all(op == "IGUAL" for cl in itens_saida + itens_entrada for _, op, _ in cl)

    assert len(itens_saida) == 6 * 4 * len(EMPRESAS)
    assert len(itens_entrada) == 6 * 4 * len(EMPRESAS)


def test_repescagem_pela_chave_e_limitada_e_so_para_pendentes_antigas(db, simulado):
    _sincronizar(db, simulado)

    por_chave = [
        cl
        for rota, cl in simulado.consultas
        if rota == ROTA_NOTAS_ENTRADA and [campo for campo, _, _ in cl] == ["chavenfe"]
    ]

    assert [dict((c, v) for c, _, v in cl)["chavenfe"] for cl in por_chave] == [chave(2)]


def test_entrada_com_coi_fora_do_catalogo_e_achada_pela_chave(db, simulado):

    simulado.entrada("3", 302, 85, cnpj("2"), 2, data="2026-10-06 15:00:00")

    _sincronizar(db, simulado)

    t = _por_chave(db)[2]
    assert (t.status, t.coi_entrada) == ("PROCESSADA", "85")
    assert (t.problemas_coi, t.entre_empresas) == ([], False)


def test_paginacao_que_repete_linhas_e_registrada(db, simulado):
    simulado.itens[ROTA_ITENS_SAIDA].append(dict(simulado.itens[ROTA_ITENS_SAIDA][0]))

    resultado = _sincronizar(db, simulado)

    assert resultado.status == "parcial"
    erros = db.scalars(
        select(IntegracaoErro).where(IntegracaoErro.tipo_erro == "PaginacaoInstavel")
    ).all()
    assert [e.id_erp_empresa for e in erros] == ["1"]
    assert _por_chave(db)[1].quantidade_itens == 2


def test_repetir_nao_duplica_nada(db, simulado):
    _sincronizar(db, simulado)
    antes = {k: (v.id, v.hash_payload, len(v.itens)) for k, v in _por_chave(db).items()}

    _sincronizar(db, simulado)

    assert {k: (v.id, v.hash_payload, len(v.itens)) for k, v in _por_chave(db).items()} == antes


def test_cancelamento_posterior_atualiza_o_status(db, simulado):
    _sincronizar(db, simulado)
    nota = next(n for n in simulado.notas[ROTA_NOTAS_SAIDA] if n["idplanilha"] == 201)
    nota["flagnotacancel"] = "T"

    _sincronizar(db, simulado)

    assert _por_chave(db)[2].status == "CANCELADA"


def test_nota_cancelada_que_perdeu_os_itens_vira_cancelada(db, simulado):
    _sincronizar(db, simulado)
    assert _por_chave(db)[2].status == "PENDENTE"

    nota = next(n for n in simulado.notas[ROTA_NOTAS_SAIDA] if n["idplanilha"] == 201)
    nota["flagnotacancel"] = "T"
    simulado.itens[ROTA_ITENS_SAIDA] = [
        i for i in simulado.itens[ROTA_ITENS_SAIDA] if i["idplanilha"] != 201
    ]

    _sincronizar(db, simulado)

    t = _por_chave(db)[2]
    assert t.status == "CANCELADA"
    assert t.raw_data["saida"]["cancelada"] is True
    assert len(t.itens) == 2


def test_pendente_que_sumiu_sem_cancelar_continua_pendente(db, simulado):
    _sincronizar(db, simulado)
    simulado.itens[ROTA_ITENS_SAIDA] = [
        i for i in simulado.itens[ROTA_ITENS_SAIDA] if i["idplanilha"] != 201
    ]

    _sincronizar(db, simulado)

    assert _por_chave(db)[2].status == "PENDENTE"


def test_le_so_as_rotas_de_consulta_liberadas(db, simulado):
    _sincronizar(db, simulado)

    assert set(simulado.rotas) <= set(ROTAS)
    execucoes = db.scalar(
        select(func.count())
        .select_from(Sincronizacao)
        .where(Sincronizacao.tipo == "transferencias")
    )

    assert execucoes == 1 + len(EMPRESAS) + 1


def test_grava_valor_emissor_cfop_e_produto_que_entrou_sem_estar_na_saida(db, simulado):

    simulado._item(ROTA_ITENS_ENTRADA, "3", 301, 7161, ONTEM, produtos=(910003,))
    _sincronizar(db, simulado)
    certa = _por_chave(db)[1]

    assert certa.valor_total == Decimal("1234.56")
    assert certa.usuario_emissao == "EMISSOR FICTICIO"
    assert [(i.valor_total, i.cfop_saida, i.cfop_entrada) for i in certa.itens] == [
        (Decimal("10.00"), "5152", "1152"),
        (Decimal("20.00"), "5152", "1152"),
    ]
    assert [i["id_produto"] for i in certa.raw_data["itens_sem_saida"]] == ["910003"]


def test_recebido_e_repartido_entre_linhas_do_mesmo_produto():
    from app.database.models import TransferenciaItem
    from app.sync.transferencias import distribuir_recebido

    linhas = [
        TransferenciaItem(id_produto_erp="9760", quantidade_solicitada=Decimal(q))
        for q in ("1000", "1000", "3000")
    ] + [TransferenciaItem(id_produto_erp="66", quantidade_solicitada=Decimal("18"))]
    distribuir_recebido(linhas, {("9760", "9760"): Decimal("5000")})
    assert [i.quantidade_processada for i in linhas] == [
        Decimal("1000"),
        Decimal("1000"),
        Decimal("3000"),
        None,
    ]

    distribuir_recebido(linhas, {("9760", "9760"): Decimal("1500"), ("66", "66"): Decimal("20")})
    assert [i.quantidade_processada for i in linhas] == [
        Decimal("1000"),
        Decimal("500"),
        Decimal("0"),
        Decimal("20"),
    ]


def _itens_da_nota(simulado, rota, planilha):
    return [i for i in simulado.itens[rota] if i["idplanilha"] == planilha]


def test_entrada_cancelada_depois_volta_a_transferencia_para_pendente(db, simulado):
    _sincronizar(db, simulado)
    assert _por_chave(db)[1].status == "PROCESSADA"

    nota = next(n for n in simulado.notas[ROTA_NOTAS_ENTRADA] if n["idplanilha"] == 301)
    nota["notacancelada"] = "T"

    _sincronizar(db, simulado)

    t = _por_chave(db)[1]
    assert (t.status, t.coi_entrada, t.id_erp_entrada, t.empresa_entrada_id) == (
        "PENDENTE",
        None,
        None,
        None,
    )
    assert t.data_processamento is None
    assert [(i.quantidade_processada, i.cfop_entrada) for i in t.itens] == [(None, None)] * 2
    assert t.raw_data["entrada_cancelada"]["id_planilha"] == "301"


def test_recebido_da_grade_vai_para_o_subproduto_certo(db, simulado):

    for item, sub in zip(_itens_da_nota(simulado, ROTA_ITENS_SAIDA, 101), (1, 2), strict=True):
        item["idproduto"], item["idsubproduto"] = 910001, sub

    entrada = _itens_da_nota(simulado, ROTA_ITENS_ENTRADA, 301)
    simulado.itens[ROTA_ITENS_ENTRADA].remove(entrada[0])
    entrada[1]["idproduto"], entrada[1]["idsubproduto"] = 910001, 2

    _sincronizar(db, simulado)

    itens = sorted(_por_chave(db)[1].itens, key=lambda i: i.codigo_produto)
    assert [(i.codigo_produto, i.quantidade_processada, i.cfop_entrada) for i in itens] == [
        ("1", None, None),
        ("2", Decimal("5.0"), "1152"),
    ]
    assert _por_chave(db)[1].raw_data["itens_sem_saida"] == []


def test_linhas_sem_sequencia_de_subprodutos_diferentes_nao_se_fundem(db, simulado):
    for item, sub in zip(_itens_da_nota(simulado, ROTA_ITENS_SAIDA, 101), (1, 2), strict=True):
        item["idproduto"], item["idsubproduto"] = 910001, sub
        del item["numsequencia"]

    _sincronizar(db, simulado)

    itens = _por_chave(db)[1].itens
    assert sorted(i.codigo_produto for i in itens) == ["1", "2"]


def test_nota_que_nao_mudou_nao_tem_os_itens_regravados(db, simulado):
    _sincronizar(db, simulado)
    antes = {k: sorted(i.id for i in t.itens) for k, t in _por_chave(db).items()}

    _sincronizar(db, simulado)

    assert {k: sorted(i.id for i in t.itens) for k, t in _por_chave(db).items()} == antes


def test_nota_que_mudou_tem_os_itens_regravados(db, simulado):
    _sincronizar(db, simulado)
    item = _itens_da_nota(simulado, ROTA_ITENS_SAIDA, 201)[0]
    item["qtdproduto"] = 99.0

    _sincronizar(db, simulado)

    quantidades = [i.quantidade_solicitada for i in _por_chave(db)[2].itens]
    assert Decimal("99") in quantidades
