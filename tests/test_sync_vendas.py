import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import func, select

from app.database.models import (
    Devolucao,
    Empresa,
    IntegracaoErro,
    Venda,
    VendaDia,
    VendaTitulo,
    Vendedor,
)
from app.erp.client import ErpApiClient
from app.erp.servicos import (
    ROTA_CAD_LOJAS,
    ROTA_ITENS_ENTRADA,
    ROTA_ITENS_SAIDA,
    ROTA_NOTAS_ENTRADA,
    ROTA_NOTAS_SAIDA,
    ROTA_RECEBIMENTOS_SAIDA,
    ServicosErp,
)
from app.sync.comum import RegistroErros
from app.sync.empresas import sincronizar_empresas
from app.sync.vendas import VERSAO_DIA, atualizar_vendedores, dias_a_ler, sincronizar_vendas
from tests.erpapi_fakes import TOKEN_PATH, criar_settings
from tests.sync_fakes import fabrica_de, pagina_json, politica

pytestmark = pytest.mark.integration

AMBIENTE = "teste-sync"
EMPRESAS = ("1", "2", "4")

AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
HOJE = "2026-10-10"
ONTEM = "2026-10-09"
ROTAS = (
    ROTA_CAD_LOJAS,
    ROTA_ITENS_SAIDA,
    ROTA_NOTAS_SAIDA,
    ROTA_RECEBIMENTOS_SAIDA,
    ROTA_ITENS_ENTRADA,
    ROTA_NOTAS_ENTRADA,
)


@pytest.fixture(autouse=True)
def _sem_dados_reais(db_vazio):
    pass


class VendasSimuladas:
    def __init__(self) -> None:
        self.lojas = [{"idempresa": int(e), "nomefantasia": f"Loja {e}"} for e in EMPRESAS]
        self.itens: list[dict] = []
        self.notas: list[dict] = []
        self.recebimentos: list[dict] = []
        self.itens_entrada: list[dict] = []
        self.notas_entrada: list[dict] = []
        self.consultas: list[tuple[str, tuple]] = []

    def recebimento(
        self,
        empresa: str,
        planilha: int,
        forma: tuple[int, str],
        valor: float,
        *,
        serie: str = "PDV",
        parcela: str = "1",
        dia: str = ONTEM,
        pago: float | None = None,
        pago_em: str | None = None,
    ) -> "VendasSimuladas":
        pago = valor if pago is None else pago
        registro = {
            "idempresa": int(empresa),
            "idplanilha": planilha,
            "idtitulo": 1,
            "digitotitulo": parcela,
            "serienota": serie,
            "idrecebimento": forma[0],
            "descrrecebimento": forma[1],
            "valtitulo": valor,
            "valtitulopago": pago,
            "valtitulopendente": valor - pago,
            "valjuroscobrado": 0.0,
            "valdescconcedidotitulo": 0.0,
            "dtmovimento": dia,
        }
        if pago:
            registro["dtultimopagamento"] = pago_em or dia
        self.recebimentos.append(registro)
        return self

    def devolucao(
        self,
        empresa: str,
        planilha: int,
        valores: tuple[float, ...],
        *,
        coi: int = 31,
        dia: str = ONTEM,
        cancelada: bool = False,
    ) -> "VendasSimuladas":
        self.notas_entrada.append(
            {
                "idempresa": int(empresa),
                "idplanilha": planilha,
                "numnota": planilha + 9000,
                "serienota": "1",
                "dtemissao": dia,
                "dtmovimento": f"{dia} 15:00:00",
                "notacancelada": "T" if cancelada else "F",
            }
        )
        for seq, valor in enumerate(valores, start=1):
            self.itens_entrada.append(
                {
                    "idempresa": int(empresa),
                    "idplanilha": planilha,
                    "idoperacao": coi,
                    "idproduto": 800 + seq,
                    "idsubproduto": 800 + seq,
                    "numsequencia": seq,
                    "qtdproduto": 1.0,
                    "dtmovimento": dia,
                    "valtotliquido": valor,
                }
            )
        return self

    def venda(
        self,
        empresa: str,
        planilha: int,
        coi: int,
        valores: tuple[float, ...],
        *,
        dia: str = ONTEM,
        emissao: str | None = None,
        cancelada: bool = False,
        cabecalho: bool = True,
        vendedor: int = 26,
    ) -> "VendasSimuladas":
        if cabecalho:
            self.notas.append(
                {
                    "idempresa": int(empresa),
                    "idplanilha": planilha,
                    "numnota": planilha + 5000,
                    "serienota": "1",
                    "modelo": "65" if coi == 8300 else "55",
                    "dtemissao": emissao or dia,
                    "dtmovimento": f"{dia} 09:30:00",
                    "flagnotacancel": "T" if cancelada else "F",
                    "valcontabil": sum(valores),
                }
            )
        for seq, valor in enumerate(valores, start=1):
            self.itens.append(
                {
                    "idempresa": int(empresa),
                    "idplanilha": planilha,
                    "idoperacao": coi,
                    "idproduto": 700 + seq,
                    "idsubproduto": 700 + seq,
                    "numsequencia": seq,
                    "qtdproduto": 2.0,
                    "descrproduto": f"PRODUTO FICTICIO {700 + seq}",
                    "dtmovimento": dia,
                    "valtotliquido": valor,
                    "valdescontopro": 1.0,
                    "cfop": 5102,
                    "idvendedor": vendedor,
                }
            )
        return self

    def pessoa(self, id_clifor: int, nome: str, *, saida: bool = True) -> "VendasSimuladas":
        (self.notas if saida else self.notas_entrada).append(
            {
                "idempresa": 2,
                "idplanilha": 8000 + len(self.notas) + len(self.notas_entrada),
                "idclifor": id_clifor,
                "nome": nome,
                "dtemissao": "2026-01-15",
            }
        )
        return self

    def consultas_em(self, rota: str) -> list[tuple]:
        return [c for r, c in self.consultas if r == rota]

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._responder)

    def _responder(self, request: httpx2.Request) -> httpx2.Response:
        request.read()
        caminho = request.url.path
        if caminho == TOKEN_PATH:
            return httpx2.Response(200, json={"access_token": "tk-ficticio", "expires_in": 3600})
        corpo = json.loads(request.content)
        clausulas = tuple((c["campo"], c["operador"], c["valor"]) for c in corpo["clausulas"])
        self.consultas.append((caminho, clausulas))
        if caminho == ROTA_CAD_LOJAS:
            return pagina_json(self.lojas if corpo["page"] == 1 else [], False)
        base = {
            ROTA_ITENS_SAIDA: self.itens,
            ROTA_NOTAS_SAIDA: self.notas,
            ROTA_RECEBIMENTOS_SAIDA: self.recebimentos,
            ROTA_ITENS_ENTRADA: self.itens_entrada,
            ROTA_NOTAS_ENTRADA: self.notas_entrada,
        }.get(caminho)
        if base is None:
            raise AssertionError(f"rota inesperada: {caminho}")
        registros = [r for r in base if _atende(r, clausulas)]
        return pagina_json(registros if corpo["page"] == 1 else [], False)


def _atende(registro: dict, clausulas: tuple) -> bool:
    for campo, operador, valor in clausulas:
        if operador != "IGUAL":
            raise AssertionError(f"filtro nao simulado: {campo} {operador}")
        if str(registro.get(campo))[:10] != valor and str(registro.get(campo)) != valor:
            return False
    return True


def _servicos(simulado: VendasSimuladas) -> ServicosErp:
    settings = criar_settings(allowed_routes=",".join(ROTAS), campo_registros="data")
    return ServicosErp(
        ErpApiClient(settings, transport=simulado.transport()),
        campo_registros="data",
        max_paginas=settings.max_pages,
    )


def _sincronizar(db, simulado, *, janela=2, historico=2, por_ciclo=0):
    sincronizar_empresas(
        fabrica_de(db),
        _servicos(simulado),
        ambiente=AMBIENTE,
        empresas_ativas=EMPRESAS,
        politica=politica()[0],
    )
    return sincronizar_vendas(
        fabrica_de(db),
        _servicos(simulado),
        ambiente=AMBIENTE,
        empresas=EMPRESAS,
        politica=politica()[0],
        janela_dias=janela,
        historico_dias=historico,
        dias_por_ciclo=por_ciclo,
        agora=lambda: AGORA,
    )


def _vendas(db) -> dict[str, Venda]:
    db.expire_all()
    return {v.id_erp: v for v in db.scalars(select(Venda))}


@pytest.fixture
def simulado() -> VendasSimuladas:
    return (
        VendasSimuladas()
        .venda("1", 11, 8300, (10.5, 4.5))
        .venda("1", 12, 3001, (200.0,))
        .venda("2", 21, 8001, (80.0, 20.0, 5.0))
        .venda("2", 22, 8300, (30.0,), cancelada=True)
        .venda("1", 13, 8300, (7.0,), dia=HOJE)
        .venda("1", 14, 3000, (999.0,))
        .venda("1", 15, 8301, (999.0,))
        .recebimento("1", 901, (8, "PIX TEF"), 15.0)
        .recebimento("1", 902, (63, "BOLETO BANCO"), 100.0, parcela="1", pago=0)
        .recebimento("1", 902, (63, "BOLETO BANCO"), 100.0, parcela="2", pago=0)
        .recebimento("1", 903, (90, "COMPRA FUNCIONARIO"), 50.0, serie="AVU")
        .recebimento("1", 904, (8, "PIX TEF"), 70.0, serie="PRE")
        .devolucao("1", 51, (3.0, 1.5))
        .devolucao("1", 52, (40.0,), coi=30, cancelada=True)
    )


def test_grava_uma_venda_por_nota_com_canal_e_total_dos_itens(db, simulado):
    resultado = _sincronizar(db, simulado)
    assert resultado.status == "sucesso", resultado.mensagem

    v = _vendas(db)
    assert sorted(v) == ["11", "12", "13", "21", "22"]
    balcao = v["11"]
    assert (balcao.canal, balcao.coi, balcao.modelo, balcao.numero_nota) == (
        "balcao",
        8300,
        "65",
        "5011",
    )
    assert balcao.data_venda == date(2026, 10, 9)
    assert balcao.valor_total == Decimal("15.00")
    assert balcao.valor_desconto == Decimal("2.00")
    assert balcao.quantidade_itens == len(balcao.itens) == 2
    assert balcao.id_vendedor == "26"
    assert [i.valor_liquido for i in balcao.itens] == [Decimal("10.5"), Decimal("4.5")]
    assert (v["12"].canal, v["21"].canal) == ("faturamento", "televendas")
    assert v["21"].valor_total == Decimal("105.00")
    assert v["13"].data_venda == date(2026, 10, 10)
    assert v["22"].cancelada is True


def test_le_so_os_cois_de_venda_e_cabecalho_so_quando_ha_venda(db, simulado):
    _sincronizar(db, simulado)

    cois = {
        dict((c, v) for c, _, v in f)["idoperacao"] for f in simulado.consultas_em(ROTA_ITENS_SAIDA)
    }
    assert cois == {"8300", "8001", "3001"}

    cabecalhos = [f for f in simulado.consultas_em(ROTA_NOTAS_SAIDA) if f[0][0] == "idempresa"]
    pedidos = sorted((dict((c, v) for c, _, v in f)["idempresa"], f[1][2]) for f in cabecalhos)
    assert pedidos == [("1", ONTEM), ("1", HOJE), ("2", ONTEM)]


def test_repetir_nao_duplica_e_reflete_cancelamento(db, simulado):
    _sincronizar(db, simulado)
    simulado.notas[0]["flagnotacancel"] = "T"
    _sincronizar(db, simulado)

    v = _vendas(db)
    assert db.scalar(select(func.count()).select_from(Venda)) == 5
    assert v["11"].cancelada is True
    assert len(v["11"].itens) == 2


def test_nota_que_sumiu_do_dia_e_apagada_na_releitura(db, simulado):
    _sincronizar(db, simulado)
    simulado.itens = [i for i in simulado.itens if i["idplanilha"] != 12]
    _sincronizar(db, simulado)

    assert "12" not in _vendas(db)


def test_nota_emitida_noutro_dia_e_lida_pelo_idplanilha(db, simulado):
    simulado.venda("1", 16, 3001, (50.0,), emissao="2026-10-02")
    _sincronizar(db, simulado)

    assert _vendas(db)["16"].valor_total == Decimal("50.00")
    filtros = [dict((c, v) for c, _, v in f) for f in simulado.consultas_em(ROTA_NOTAS_SAIDA)]
    assert {"idempresa": "1", "idplanilha": "16"} in filtros


def test_nota_sem_cabecalho_deixa_o_dia_para_o_proximo_ciclo(db, simulado):
    simulado.venda("2", 23, 8300, (9.0,), cabecalho=False)
    resultado = _sincronizar(db, simulado)

    assert resultado.status == "parcial"
    assert "23" not in _vendas(db)
    empresa_2 = db.scalar(
        select(Empresa.id).where(Empresa.id_erp == "2", Empresa.ambiente == AMBIENTE)
    )
    dias = set(db.scalars(select(VendaDia.dia).where(VendaDia.empresa_id == empresa_2)))
    assert date(2026, 10, 9) not in dias
    assert date(2026, 10, 10) in dias
    tipos = set(db.scalars(select(IntegracaoErro.tipo_erro)))
    assert "NotaSemCabecalho" in tipos


def _dia_lido(db, id_erp: str, dia: date) -> VendaDia | None:
    db.expire_all()
    empresa = db.scalar(
        select(Empresa.id).where(Empresa.id_erp == id_erp, Empresa.ambiente == AMBIENTE)
    )
    return db.get(VendaDia, (empresa, dia))


def test_dia_que_volta_vazio_nao_apaga_as_vendas_ja_gravadas(db, simulado):
    assert _sincronizar(db, simulado).status == "sucesso"

    simulado.itens = [
        i for i in simulado.itens if not (i["idempresa"] == 1 and i["dtmovimento"] == ONTEM)
    ]
    simulado.itens_entrada = [i for i in simulado.itens_entrada if i["idempresa"] != 1]

    resultado = _sincronizar(db, simulado)

    assert resultado.status == "parcial"
    assert {"11", "12"} <= set(_vendas(db))
    assert db.scalar(select(func.count()).select_from(Devolucao)) == 1
    assert "DiaVazioPreservado" in set(db.scalars(select(IntegracaoErro.tipo_erro)))
    dia = _dia_lido(db, "1", date(2026, 10, 9))
    assert dia is not None and dia.notas == 2


def test_releitura_sem_cabecalho_nao_substitui_o_dia_ja_gravado(db, simulado):
    assert _sincronizar(db, simulado).status == "sucesso"

    simulado.notas = [n for n in simulado.notas if n["idplanilha"] != 21]

    assert _sincronizar(db, simulado).status == "parcial"

    assert {"21", "22"} <= set(_vendas(db))


def test_dias_lidos_ficam_registrados_inclusive_sem_venda(db, simulado):
    _sincronizar(db, simulado)

    linhas = db.execute(
        select(Empresa.id_erp, VendaDia.dia, VendaDia.notas)
        .join(Empresa, Empresa.id == VendaDia.empresa_id)
        .order_by(Empresa.id_erp, VendaDia.dia)
    ).all()
    assert linhas == [
        ("1", date(2026, 10, 9), 2),
        ("1", date(2026, 10, 10), 1),
        ("2", date(2026, 10, 9), 2),
        ("2", date(2026, 10, 10), 0),
        ("4", date(2026, 10, 9), 0),
        ("4", date(2026, 10, 10), 0),
    ]


def test_historico_le_os_dias_mais_recentes_que_faltam(db):
    empresa = Empresa(id_erp="1", codigo="1", nome="Loja 1", ambiente=AMBIENTE)
    db.add(empresa)
    db.flush()
    for dia in (date(2026, 10, 7), date(2026, 10, 5)):
        db.add(
            VendaDia(
                empresa_id=empresa.id, dia=dia, notas=1, versao=VERSAO_DIA, sincronizado_em=AGORA
            )
        )
    db.flush()

    dias = dias_a_ler(
        db, empresa.id, hoje=date(2026, 10, 10), janela_dias=2, historico_dias=8, dias_por_ciclo=3
    )

    assert dias == [
        date(2026, 10, 10),
        date(2026, 10, 9),
        date(2026, 10, 8),
        date(2026, 10, 6),
        date(2026, 10, 4),
    ]

    todos = dias_a_ler(
        db, empresa.id, hoje=date(2026, 10, 10), janela_dias=2, historico_dias=8, dias_por_ciclo=99
    )
    assert min(todos) == date(2026, 10, 3)


def _titulos(db) -> list[tuple]:
    db.expire_all()
    return db.execute(
        select(
            VendaTitulo.id_planilha,
            VendaTitulo.parcela,
            VendaTitulo.forma,
            VendaTitulo.dia_lancamento,
            VendaTitulo.dia_pagamento,
            VendaTitulo.valor,
            VendaTitulo.valor_pago,
            VendaTitulo.valor_pendente,
        ).order_by(VendaTitulo.id_planilha, VendaTitulo.parcela)
    ).all()


def test_titulos_do_dia_com_forma_pago_e_pendente(db, simulado):
    _sincronizar(db, simulado)

    ontem = date(2026, 10, 9)

    assert _titulos(db) == [
        ("901", "1", "PIX TEF", ontem, ontem, Decimal("15.00"), Decimal("15.00"), Decimal("0.00")),
        (
            "902",
            "1",
            "BOLETO BANCO",
            ontem,
            None,
            Decimal("100.00"),
            Decimal("0.00"),
            Decimal("100.00"),
        ),
        (
            "902",
            "2",
            "BOLETO BANCO",
            ontem,
            None,
            Decimal("100.00"),
            Decimal("0.00"),
            Decimal("100.00"),
        ),
    ]
    pagos = [dict((c, v) for c, _, v in f) for f in simulado.consultas_em(ROTA_RECEBIMENTOS_SAIDA)]

    assert {(p.get("dtultimopagamento"), p.get("dtmovimento")) for p in pagos} >= {
        (HOJE, None),
        (ONTEM, None),
        (None, ONTEM),
    }


def test_boleto_de_venda_antiga_pago_hoje_entra_como_recebido_hoje(db, simulado):
    _sincronizar(db, simulado)

    boleto = next(r for r in simulado.recebimentos if r["idplanilha"] == 902)
    boleto.update(valtitulopago=100.0, valtitulopendente=0.0, dtultimopagamento=HOJE)
    simulado.recebimento(
        "1", 800, (63, "BOLETO BANCO"), 300.0, dia="2026-09-01", pago=300.0, pago_em=HOJE
    )

    simulado.recebimentos = [
        r for r in simulado.recebimentos if r is boleto or r["idplanilha"] == 800
    ]
    _sincronizar(db, simulado, janela=1)

    hoje = date(2026, 10, 10)
    titulos = {(t[0], t[1]): t for t in _titulos(db)}
    assert titulos[("800", "1")][3:] == (
        date(2026, 9, 1),
        hoje,
        Decimal("300.00"),
        Decimal("300.00"),
        Decimal("0.00"),
    )
    assert titulos[("902", "1")][3:] == (
        date(2026, 10, 9),
        hoje,
        Decimal("100.00"),
        Decimal("100.00"),
        Decimal("0.00"),
    )
    assert titulos[("902", "2")][4:] == (
        None,
        Decimal("100.00"),
        Decimal("0.00"),
        Decimal("100.00"),
    )


def test_recebimento_estornado_volta_a_pendente(db, simulado):
    simulado.recebimento("1", 905, (8, "PIX TEF"), 40.0, dia="2026-09-01", pago_em=ONTEM)
    _sincronizar(db, simulado)
    assert _titulos(db)[-1][4] == date(2026, 10, 9)

    simulado.recebimentos = [r for r in simulado.recebimentos if r["idplanilha"] != 905]
    _sincronizar(db, simulado)

    estornado = next(t for t in _titulos(db) if t[0] == "905")
    assert estornado[4:] == (None, Decimal("40.00"), Decimal("0.00"), Decimal("40.00"))


def test_leitura_de_pagos_vazia_nao_desfaz_os_recebidos_do_dia(db, simulado):
    simulado.recebimento("1", 905, (8, "PIX TEF"), 40.0, dia="2026-09-01", pago_em=ONTEM)
    _sincronizar(db, simulado)
    simulado.recebimentos = [r for r in simulado.recebimentos if r["idplanilha"] != 905]
    simulado.recebimentos = [r for r in simulado.recebimentos if r["idplanilha"] == 902]

    _sincronizar(db, simulado)

    assert next(t for t in _titulos(db) if t[0] == "905")[4] == date(2026, 10, 9)


def test_devolucoes_gravadas_sem_a_cancelada(db, simulado):
    _sincronizar(db, simulado)

    devolucoes = db.execute(
        select(Devolucao.id_erp, Devolucao.coi, Devolucao.valor_total, Devolucao.quantidade_itens)
    ).all()
    assert devolucoes == [("51", 31, Decimal("4.50"), 2)]
    entradas = [dict((c, v) for c, _, v in f) for f in simulado.consultas_em(ROTA_ITENS_ENTRADA)]
    assert {e["idoperacao"] for e in entradas} == {"30", "31"}


def test_releitura_substitui_titulos_e_devolucoes(db, simulado):
    _sincronizar(db, simulado)
    simulado.recebimentos = [r for r in simulado.recebimentos if r["idplanilha"] != 901]
    simulado.notas_entrada[0]["notacancelada"] = "T"
    _sincronizar(db, simulado)

    assert db.scalar(select(func.count()).select_from(Devolucao)) == 0
    assert {f for (f,) in db.execute(select(VendaTitulo.forma))} == {"BOLETO BANCO"}


def test_dia_lido_na_versao_antiga_volta_para_o_historico(db):
    empresa = Empresa(id_erp="1", codigo="1", nome="Loja 1", ambiente=AMBIENTE)
    db.add(empresa)
    db.flush()
    db.add(VendaDia(empresa_id=empresa.id, dia=date(2026, 10, 7), notas=1, sincronizado_em=AGORA))
    db.add(
        VendaDia(
            empresa_id=empresa.id,
            dia=date(2026, 10, 6),
            notas=1,
            versao=VERSAO_DIA,
            sincronizado_em=AGORA,
        )
    )
    db.flush()

    dias = dias_a_ler(
        db, empresa.id, hoje=date(2026, 10, 10), janela_dias=2, historico_dias=5, dias_por_ciclo=9
    )

    assert dias == [date(2026, 10, 10), date(2026, 10, 9), date(2026, 10, 8), date(2026, 10, 7)]


def _nomes(db) -> dict[str, str | None]:
    db.expire_all()
    return {v.id_erp: v.nome for v in db.scalars(select(Vendedor))}


def test_nome_do_vendedor_pelas_notas_em_que_foi_cliente(db, simulado):
    (
        simulado.venda("2", 23, 8300, (9.0,), vendedor=31)
        .pessoa(26, "VENDEDOR FICTICIO")
        .pessoa(26, "VENDEDOR FICTICIO")
        .pessoa(26, "NOME ANTIGO")
        .pessoa(31, "OUTRO VENDEDOR", saida=False)
    )
    assert _sincronizar(db, simulado).status == "sucesso"

    assert _nomes(db) == {"26": "VENDEDOR FICTICIO", "31": "OUTRO VENDEDOR"}
    assert simulado.consultas_em(ROTA_NOTAS_SAIDA).count((("idclifor", "IGUAL", "26"),)) == 1


def test_vendedor_sem_nome_so_e_consultado_de_novo_depois_de_uma_semana(db, simulado):
    _sincronizar(db, simulado)
    assert _nomes(db) == {"26": None}
    pessoa = (("idclifor", "IGUAL", "26"),)
    assert simulado.consultas_em(ROTA_NOTAS_SAIDA).count(pessoa) == 1
    assert simulado.consultas_em(ROTA_NOTAS_ENTRADA).count(pessoa) == 1

    simulado.pessoa(26, "VENDEDOR FICTICIO")
    fabrica = fabrica_de(db)
    erros = RegistroErros(fabrica, None)
    for dias, achados in ((6, 0), (8, 1)):
        assert (
            atualizar_vendedores(
                fabrica,
                _servicos(simulado),
                politica=politica()[0],
                erros=erros,
                agora=lambda d=dias: AGORA + timedelta(days=d),
            )
            == achados
        )
    assert simulado.consultas_em(ROTA_NOTAS_SAIDA).count(pessoa) == 2
    assert _nomes(db) == {"26": "VENDEDOR FICTICIO"}
