import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import select, update

from app.database.models import (
    Empresa,
    IntegracaoErro,
    MovimentoEstoque,
    MovimentoEstoqueDia,
    NotaMovimento,
)
from app.dominio.operacoes_estoque import CATALOGO
from app.erp.client import ErpApiClient
from app.erp.servicos import (
    ROTA_CAD_LOJAS,
    ROTA_ITENS_ENTRADA,
    ROTA_ITENS_SAIDA,
    ROTA_NOTAS_ENTRADA,
    ROTA_NOTAS_SAIDA,
    ServicosErp,
)
from app.sync.empresas import sincronizar_empresas
from app.sync.movimentos import dias_a_ler, sincronizar_movimentos
from tests.erpapi_fakes import TOKEN_PATH, criar_settings
from tests.sync_fakes import fabrica_de, pagina_json, politica

pytestmark = pytest.mark.integration

AMBIENTE = "teste-sync"
EMPRESAS = ("1", "3")

AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
HOJE = "2026-10-10"
ONTEM = "2026-10-09"
ROTAS = (
    ROTA_CAD_LOJAS,
    ROTA_ITENS_SAIDA,
    ROTA_ITENS_ENTRADA,
    ROTA_NOTAS_SAIDA,
    ROTA_NOTAS_ENTRADA,
)


@pytest.fixture(autouse=True)
def _sem_dados_reais(db_vazio):
    pass


class MovimentosSimulados:
    def __init__(self) -> None:
        self.lojas = [{"idempresa": int(e), "nomefantasia": f"Loja {e}"} for e in EMPRESAS]
        self.saida: list[dict] = []
        self.entrada: list[dict] = []
        self.notas_saida: list[dict] = []
        self.notas_entrada: list[dict] = []
        self.consultas: list[tuple[str, tuple]] = []

    def nota(
        self,
        empresa: str,
        planilha: int,
        *,
        saida: bool,
        hora: str,
        usuario: str | None = None,
        **extras: object,
    ) -> "MovimentosSimulados":
        registro = {
            "idempresa": int(empresa),
            "idplanilha": planilha,
            "numnota": planilha * 10,
            "dtmovimento": f"{ONTEM} {hora}",
            "dtemissao": ONTEM,
            **extras,
        }
        if saida:
            self.notas_saida.append({**registro, "nomeusuario": usuario})
        else:
            self.notas_entrada.append(registro)
        return self

    def item(
        self,
        empresa: str,
        coi: int,
        planilha: int,
        quantidade: float,
        valor: float,
        *,
        produto: int = 501,
        seq: int = 1,
        dia: str = ONTEM,
    ) -> "MovimentosSimulados":
        registro = {
            "idempresa": int(empresa),
            "idplanilha": planilha,
            "idoperacao": coi,
            "idproduto": produto,
            "idsubproduto": produto,
            "numsequencia": seq,
            "qtdproduto": quantidade,
            "valtotliquido": valor,
            "dtmovimento": dia,
        }
        if (False, coi) in CATALOGO:
            self.entrada.append(registro)
        else:
            self.saida.append({**registro, "descrproduto": f"PRODUTO FICTICIO {produto}"})
        return self

    def consultas_em(self, rota: str) -> list[dict[str, str]]:
        return [{c: v for c, _, v in f} for r, f in self.consultas if r == rota]

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
            ROTA_ITENS_SAIDA: self.saida,
            ROTA_ITENS_ENTRADA: self.entrada,
            ROTA_NOTAS_SAIDA: self.notas_saida,
            ROTA_NOTAS_ENTRADA: self.notas_entrada,
        }.get(caminho)
        if base is None:
            raise AssertionError(f"rota inesperada: {caminho}")
        registros = [r for r in base if _atende(r, clausulas)]
        return pagina_json(registros if corpo["page"] == 1 else [], False)


def _atende(registro: dict, clausulas: tuple) -> bool:
    for campo, operador, valor in clausulas:
        if operador == "MAIOR" and campo == "idoperacao":
            if int(registro[campo]) <= int(valor):
                return False
        elif operador != "IGUAL":
            raise AssertionError(f"filtro nao simulado: {campo} {operador}")
        elif str(registro.get(campo)) != valor:
            return False
    return True


def _servicos(simulado: MovimentosSimulados) -> ServicosErp:
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
    return sincronizar_movimentos(
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


def _movimentos(db) -> list[MovimentoEstoque]:
    db.expire_all()
    return list(
        db.scalars(select(MovimentoEstoque).order_by(MovimentoEstoque.id_planilha, "sequencia"))
    )


def _empresa_id(db, id_erp: str) -> int:
    return db.scalar(
        select(Empresa.id).where(Empresa.ambiente == AMBIENTE, Empresa.id_erp == id_erp)
    )


@pytest.fixture
def simulado() -> MovimentosSimulados:
    return (
        MovimentosSimulados()
        .item("1", 80, 101, 30.0, 258.91)
        .item("1", 8080, 102, 2.0, 40.0)
        .item("1", 2000, 103, -96.0, -67.2, produto=601)
        .item("1", 2000, 103, 5.0, 12.5, produto=602, seq=2)
        .item("3", 2000, 301, 1.0, 9.9, dia=HOJE)
    )


def test_grava_o_efeito_no_estoque_com_tipo_e_documento(db, simulado):
    resultado = _sincronizar(db, simulado)
    assert resultado.status == "sucesso", resultado.mensagem

    m = {(x.id_planilha, x.sequencia): x for x in _movimentos(db)}
    assert sorted(m) == [("101", "1"), ("102", "1"), ("103", "1"), ("103", "2"), ("301", "1")]

    entrada = m[("101", "1")]
    assert (entrada.tipo, entrada.coi, entrada.dia) == ("entrada_avulsa", 80, date(2026, 10, 9))
    assert (entrada.quantidade, entrada.valor) == (Decimal("30"), Decimal("258.91"))
    assert entrada.descricao_produto is None

    saida = m[("102", "1")]
    assert (saida.tipo, saida.coi) == ("saida_avulsa", 8080)
    assert (saida.quantidade, saida.valor) == (Decimal("-2"), Decimal("-40"))

    falta, sobra = m[("103", "1")], m[("103", "2")]
    assert (falta.tipo, falta.quantidade, falta.valor) == (
        "balanco",
        Decimal("-96"),
        Decimal("-67.2"),
    )
    assert (sobra.quantidade, sobra.valor) == (Decimal("5"), Decimal("12.5"))
    assert falta.descricao_produto == "PRODUTO FICTICIO 601"

    assert m[("301", "1")].dia == date(2026, 10, 10)


def _cois_consultados(simulado, rota):
    return {int(c["idoperacao"]) for c in simulado.consultas_em(rota) if "idoperacao" in c}


def test_le_cada_coi_do_catalogo_so_nos_lados_e_dias_com_item(db, simulado):
    _sincronizar(db, simulado)

    saida = {c for lado, c in CATALOGO if lado}
    entrada = {c for lado, c in CATALOGO if not lado}
    assert _cois_consultados(simulado, ROTA_ITENS_SAIDA) == saida | {-1}
    assert _cois_consultados(simulado, ROTA_ITENS_ENTRADA) == entrada | {-1}

    por_dia = [
        (c["idempresa"], c["dtmovimento"])
        for c in simulado.consultas_em(ROTA_ITENS_ENTRADA)
        if c.get("idoperacao") != "-1"
    ]
    assert set(por_dia) == {("1", ONTEM)}


def test_livro_grava_venda_e_transferencia_com_categoria_sinal_e_operacao(db, simulado):
    simulado.item("1", 8300, 401, 3.0, 30.0)
    simulado.item("1", 85, 402, 7.0, 70.0)
    simulado.item("1", 3000, 403, 1.0, 10.0)
    simulado.saida[-2]["descroperacao"] = "Venda de Mercadoria ECF "

    assert _sincronizar(db, simulado).status == "sucesso"

    m = {x.id_planilha: x for x in _movimentos(db)}
    assert (m["401"].tipo, m["401"].quantidade, m["401"].valor) == (
        "venda",
        Decimal("-3"),
        Decimal("-30"),
    )
    assert m["401"].operacao == "Venda de Mercadoria ECF"
    assert (m["402"].tipo, m["402"].quantidade) == ("transferencia_entrada", Decimal("7"))
    assert m["403"].tipo == "venda"


def test_coi_fora_do_catalogo_e_achado_pela_varredura(db, simulado):
    simulado.item("1", 9999, 501, 4.0, 40.0)

    assert _sincronizar(db, simulado).status == "sucesso"

    novo = next(x for x in _movimentos(db) if x.coi == 9999)
    assert (novo.tipo, novo.quantidade) == ("nao_classificado", Decimal("-4"))


def test_dia_lido_antes_do_livro_volta_para_o_historico(db, simulado):
    _sincronizar(db, simulado, janela=1, historico=10, por_ciclo=1)
    um = _empresa_id(db, "1")
    db.query(MovimentoEstoqueDia).filter_by(empresa_id=um).update({"versao": 1})
    db.flush()

    assert dias_a_ler(
        db, um, hoje=date(2026, 10, 10), janela_dias=1, historico_dias=10, dias_por_ciclo=1
    ) == [date(2026, 10, 10), date(2026, 10, 9)]


def test_repetir_nao_duplica_e_item_que_sumiu_e_apagado(db, simulado):
    _sincronizar(db, simulado)
    simulado.saida = [r for r in simulado.saida if r["idplanilha"] != 102]

    _sincronizar(db, simulado)

    planilhas = sorted(x.id_planilha for x in _movimentos(db))
    assert planilhas == ["101", "103", "103", "301"]


def test_dias_lidos_ficam_registrados_inclusive_sem_movimento(db, simulado):
    _sincronizar(db, simulado)
    db.expire_all()

    dias = {(d.empresa_id, d.dia): d.movimentos for d in db.scalars(select(MovimentoEstoqueDia))}
    um, tres = _empresa_id(db, "1"), _empresa_id(db, "3")
    assert dias == {
        (um, date(2026, 10, 9)): 4,
        (um, date(2026, 10, 10)): 0,
        (tres, date(2026, 10, 9)): 0,
        (tres, date(2026, 10, 10)): 1,
    }


def test_historico_le_os_dias_mais_recentes_que_faltam(db, simulado):
    _sincronizar(db, simulado, janela=1, historico=10, por_ciclo=3)
    db.expire_all()
    um = _empresa_id(db, "1")

    assert dias_a_ler(
        db, um, hoje=date(2026, 10, 10), janela_dias=1, historico_dias=10, dias_por_ciclo=3
    ) == [date(2026, 10, 10), date(2026, 10, 6), date(2026, 10, 5), date(2026, 10, 4)]


def test_paginacao_repetida_deixa_o_dia_para_o_historico(db, simulado):
    simulado.saida.append(dict(simulado.saida[-2]))

    resultado = _sincronizar(db, simulado)

    assert resultado.status == "parcial"
    db.expire_all()
    um = _empresa_id(db, "1")
    lidos = set(
        db.scalars(select(MovimentoEstoqueDia.dia).where(MovimentoEstoqueDia.empresa_id == um))
    )
    assert lidos == {date(2026, 10, 10)}

    assert len([x for x in _movimentos(db) if x.id_planilha == "103"]) == 2
    tipos = set(db.scalars(select(IntegracaoErro.tipo_erro)))
    assert "PaginacaoInstavel" in tipos


def test_releitura_incompleta_nao_substitui_o_dia_ja_gravado(db, simulado):
    assert _sincronizar(db, simulado).status == "sucesso"

    simulado.saida = [r for r in simulado.saida if r["idplanilha"] != 102]
    simulado.saida.append(dict(simulado.saida[-2]))

    assert _sincronizar(db, simulado).status == "parcial"

    planilhas = sorted(x.id_planilha for x in _movimentos(db))
    assert planilhas == ["101", "102", "103", "103", "301"]


def test_dia_que_volta_vazio_nao_apaga_o_que_ja_estava_gravado(db, simulado):
    assert _sincronizar(db, simulado).status == "sucesso"

    simulado.saida = [r for r in simulado.saida if r["idempresa"] != 1]
    simulado.entrada = [r for r in simulado.entrada if r["idempresa"] != 1]

    resultado = _sincronizar(db, simulado)

    assert resultado.status == "parcial"
    planilhas = sorted(x.id_planilha for x in _movimentos(db))
    assert planilhas == ["101", "102", "103", "103", "301"]
    assert "DiaVazioPreservado" in set(db.scalars(select(IntegracaoErro.tipo_erro)))
    um = _empresa_id(db, "1")
    dia = db.get(MovimentoEstoqueDia, (um, date(2026, 10, 9)))
    assert dia is not None and dia.movimentos == 4


def test_item_sem_subproduto_grava_o_codigo_do_produto(db, simulado):
    del simulado.saida[0]["idsubproduto"]

    assert _sincronizar(db, simulado).status == "sucesso"

    saida = next(x for x in _movimentos(db) if x.id_planilha == "102")
    assert (saida.id_produto, saida.id_subproduto) == ("501", "501")


def _notas(db) -> dict[str, NotaMovimento]:
    db.expire_all()
    return {n.id_planilha: n for n in db.scalars(select(NotaMovimento))}


def test_le_a_hora_e_quem_lancou_no_cabecalho_das_notas(db, simulado):
    simulado.item("1", 8300, 401, 3.0, 30.0).nota(
        "1", 401, saida=True, hora="13:50:15", usuario="ANTONIA"
    )
    simulado.item("1", 11, 402, 7.0, 70.0).nota("1", 402, saida=False, hora="08:42:09")
    simulado.item("1", 8045, 403, 1.0, 10.0)

    assert _sincronizar(db, simulado).status == "sucesso"

    notas = _notas(db)
    venda, compra, sem = notas["401"], notas["402"], notas["403"]

    assert (venda.saida, venda.encontrado, venda.usuario, venda.numero) == (
        True,
        True,
        "ANTONIA",
        "4010",
    )
    assert venda.momento == datetime(2026, 10, 9, 17, 50, 15, tzinfo=UTC)
    assert (compra.saida, compra.usuario) == (False, None)
    assert compra.momento == datetime(2026, 10, 9, 12, 42, 9, tzinfo=UTC)
    assert (sem.encontrado, sem.momento) == (False, None)

    assert not {"101", "102", "103", "301"} & set(notas)


def test_cabecalho_ja_gravado_nao_e_lido_de_novo(db, simulado):
    simulado.item("1", 8300, 401, 3.0, 30.0).nota("1", 401, saida=True, hora="10:00:00")
    _sincronizar(db, simulado)
    lidas = len(simulado.consultas_em(ROTA_NOTAS_SAIDA))

    _sincronizar(db, simulado)

    assert lidas == 1
    assert len(simulado.consultas_em(ROTA_NOTAS_SAIDA)) == lidas


def test_saida_com_muitos_documentos_le_os_emitidos_no_dia_de_uma_vez(db, simulado):
    for planilha in range(500, 530):
        simulado.item("1", 8300, planilha, 1.0, 1.0).nota(
            "1", planilha, saida=True, hora="09:00:00", usuario="CAIXA"
        )

    assert _sincronizar(db, simulado).status == "sucesso"

    consultas = simulado.consultas_em(ROTA_NOTAS_SAIDA)
    assert consultas == [{"idempresa": "1", "dtemissao": ONTEM}]
    assert sum(1 for n in _notas(db).values() if n.usuario == "CAIXA") == 30


CNPJ_LOJA_1 = "11111111000101"
CNPJ_LOJA_3 = "11111111000303"


def _com_cnpjs(simulado: MovimentosSimulados) -> MovimentosSimulados:
    for loja, cnpj in zip(simulado.lojas, (CNPJ_LOJA_1, CNPJ_LOJA_3), strict=True):
        loja["cnpj"] = cnpj
    return simulado


def test_grava_o_destinatario_e_se_a_nota_esta_cancelada(db, simulado):
    _com_cnpjs(simulado)
    simulado.item("1", 8038, 601, 5.0, 45.55).nota(
        "1", 601, saida=True, hora="09:28:16", cnpjcpf=CNPJ_LOJA_3, nome="LOJA FICTICIA 3"
    )
    simulado.item("1", 8300, 602, 1.0, 10.0).nota(
        "1", 602, saida=True, hora="10:00:00", cnpjcpf="99999999000199", flagnotacancel="T"
    )

    assert _sincronizar(db, simulado).status == "sucesso"

    notas = _notas(db)
    epi, venda = notas["601"], notas["602"]
    assert (epi.cnpj_destinatario, epi.nome_destinatario, epi.cancelada) == (
        CNPJ_LOJA_3,
        "LOJA FICTICIA 3",
        False,
    )
    assert (venda.cnpj_destinatario, venda.cancelada) == ("99999999000199", True)
    assert epi.destinatario_lido and venda.destinatario_lido


def test_nota_da_empresa_errada_e_lida_de_novo_ate_ser_cancelada(db, simulado):
    _com_cnpjs(simulado)
    simulado.item("1", 8038, 601, 5.0, 45.55).nota(
        "1", 601, saida=True, hora="09:28:16", cnpjcpf=CNPJ_LOJA_3
    )

    simulado.item("1", 8040, 602, 1.0, 10.0).nota(
        "1", 602, saida=True, hora="10:00:00", cnpjcpf=CNPJ_LOJA_3
    )
    simulado.item("1", 8300, 603, 1.0, 10.0).nota(
        "1", 603, saida=True, hora="11:00:00", cnpjcpf="99999999000199"
    )
    _sincronizar(db, simulado)
    simulado.consultas.clear()

    _sincronizar(db, simulado)

    relidas = [c["idplanilha"] for c in simulado.consultas_em(ROTA_NOTAS_SAIDA)]
    assert relidas == ["601"]

    simulado.notas_saida[0]["flagnotacancel"] = "T"
    _sincronizar(db, simulado)
    assert _notas(db)["601"].cancelada is True
    simulado.consultas.clear()

    _sincronizar(db, simulado)

    assert simulado.consultas_em(ROTA_NOTAS_SAIDA) == []


def test_cabecalho_gravado_antes_do_destinatario_e_lido_de_novo(db, simulado):
    simulado.item("1", 8300, 401, 3.0, 30.0).nota(
        "1", 401, saida=True, hora="10:00:00", cnpjcpf="99999999000199"
    )
    _sincronizar(db, simulado)
    db.execute(update(NotaMovimento).values(cnpj_destinatario=None, destinatario_lido=False))
    simulado.consultas.clear()

    _sincronizar(db, simulado)

    assert len(simulado.consultas_em(ROTA_NOTAS_SAIDA)) == 1
    assert _notas(db)["401"].cnpj_destinatario == "99999999000199"


FORNECEDOR = {"cnpjcpf": "11222333000181", "nome": "FORNECEDOR FICTICIO LTDA"}


def test_grava_o_emitente_da_compra_como_fornecedor(db, simulado):
    simulado.item("1", 11, 402, 7.0, 70.0).nota(
        "1", 402, saida=False, hora="08:42:09", **FORNECEDOR
    )
    simulado.item("1", 8300, 401, 3.0, 30.0).nota(
        "1", 401, saida=True, hora="10:00:00", cnpjcpf="99999999000199", nome="CLIENTE"
    )

    assert _sincronizar(db, simulado).status == "sucesso"

    notas = _notas(db)
    compra, venda = notas["402"], notas["401"]
    assert (compra.cnpj_emitente, compra.nome_emitente, compra.emitente_lido) == (
        "11222333000181",
        "FORNECEDOR FICTICIO LTDA",
        True,
    )

    assert (venda.cnpj_emitente, venda.nome_emitente) == (None, None)


def test_entrada_gravada_antes_do_emitente_e_lida_de_novo(db, simulado):
    simulado.item("1", 11, 402, 7.0, 70.0).nota(
        "1", 402, saida=False, hora="08:42:09", **FORNECEDOR
    )
    _sincronizar(db, simulado)
    db.execute(update(NotaMovimento).values(nome_emitente=None, emitente_lido=False))
    simulado.consultas.clear()

    _sincronizar(db, simulado)

    assert len(simulado.consultas_em(ROTA_NOTAS_ENTRADA)) == 1
    assert _notas(db)["402"].nome_emitente == "FORNECEDOR FICTICIO LTDA"
    simulado.consultas.clear()

    _sincronizar(db, simulado)

    assert simulado.consultas_em(ROTA_NOTAS_ENTRADA) == []


def _compra_antiga(db, planilha: str) -> None:
    db.add(
        MovimentoEstoque(
            empresa_id=_empresa_id(db, "1"),
            dia=date(2026, 9, 1),
            coi=11,
            tipo="compra",
            id_planilha=planilha,
            sequencia="1",
            id_produto="501",
            id_subproduto="501",
            quantidade=Decimal("4"),
            valor=Decimal("40"),
            sincronizado_em=AGORA,
        )
    )
    db.flush()


def test_compras_do_historico_sem_fornecedor_sao_lidas_depois_dos_dias(db, simulado):
    _sincronizar(db, simulado)
    _compra_antiga(db, "900")
    _compra_antiga(db, "901")
    db.add(
        NotaMovimento(
            empresa_id=_empresa_id(db, "1"),
            id_planilha="901",
            saida=False,
            encontrado=True,
            sincronizado_em=AGORA,
        )
    )
    db.flush()
    simulado.nota("1", 900, saida=False, hora="09:00:00", **FORNECEDOR)
    simulado.nota("1", 901, saida=False, hora="09:00:00", cnpjcpf="22222222000122", nome="OUTRO")
    simulado.consultas.clear()

    assert _sincronizar(db, simulado).status == "sucesso"

    notas = _notas(db)
    assert notas["900"].nome_emitente == "FORNECEDOR FICTICIO LTDA"
    assert (notas["901"].nome_emitente, notas["901"].emitente_lido) == ("OUTRO", True)
    simulado.consultas.clear()

    _sincronizar(db, simulado)

    assert simulado.consultas_em(ROTA_NOTAS_ENTRADA) == []
