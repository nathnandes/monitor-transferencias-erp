import logging
from datetime import UTC, datetime

import httpx2
import pytest
from sqlalchemy import select

from app.database.models import (
    Empresa,
    EstoqueConsolidado,
    EstoqueEmpresaLocalLote,
    IntegracaoErro,
    Sincronizacao,
)
from app.sync.empresas import sincronizar_empresas
from app.sync.estoque import sincronizar_estoque
from tests.erpapi_fakes import CLIENT_SECRET, SENHA
from tests.sync_fakes import (
    TOKEN,
    ErpApiSimulado,
    dec,
    fabrica_de,
    loja,
    politica,
    saldo,
    servicos_para,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _sem_dados_reais(db_vazio):
    pass


AMBIENTE = "teste-sync"
EMPRESAS = ("1", "2", "3", "4", "5", "6")


def _sync_empresas(db, simulado, empresas=EMPRESAS):
    return sincronizar_empresas(
        fabrica_de(db),
        servicos_para(simulado),
        ambiente=AMBIENTE,
        empresas_ativas=empresas,
        politica=politica()[0],
    )


def _sync_estoque(db, simulado, empresas=EMPRESAS, tentativas=3, completa=False):
    regra, _ = politica(tentativas)
    return sincronizar_estoque(
        fabrica_de(db),
        servicos_para(simulado),
        ambiente=AMBIENTE,
        empresas=empresas,
        politica=regra,
        completa=completa,
    )


def _lojas(*ids):
    return [loja(i, f"Loja Ficticia {i}") for i in ids]


@pytest.fixture
def com_empresas(db):
    simulado = ErpApiSimulado()
    simulado.lojas = _lojas(*EMPRESAS)
    _sync_empresas(db, simulado)
    return db


def _linhas(db, ativo=None):
    consulta = (
        select(EstoqueEmpresaLocalLote)
        .join(Empresa)
        .where(Empresa.ambiente == AMBIENTE)
        .order_by(EstoqueEmpresaLocalLote.id)
    )
    if ativo is not None:
        consulta = consulta.where(EstoqueEmpresaLocalLote.ativo.is_(ativo))
    db.expire_all()
    return db.scalars(consulta).all()


def _consolidado(db, produto, sub="1"):
    db.expire_all()
    return db.scalar(
        select(EstoqueConsolidado).where(
            EstoqueConsolidado.id_produto == produto, EstoqueConsolidado.id_subproduto == sub
        )
    )


def _execucao(db, execucao_id):
    db.expire_all()
    return db.get(Sincronizacao, execucao_id)


def _filhas(db, pai_id):
    db.expire_all()
    return {
        s.empresa.id_erp: s
        for s in db.scalars(
            select(Sincronizacao).where(Sincronizacao.sincronizacao_pai_id == pai_id)
        )
    }


def _erros(db, execucao_ids):
    return db.scalars(
        select(IntegracaoErro)
        .where(IntegracaoErro.sincronizacao_id.in_(execucao_ids))
        .order_by(IntegracaoErro.id)
    ).all()


def _todos_os_ids(db, pai_id):
    return [pai_id, *(s.id for s in _filhas(db, pai_id).values())]


def test_sincroniza_empresas_e_e_idempotente(db):
    simulado = ErpApiSimulado()
    simulado.lojas = [*_lojas(*EMPRESAS), loja("9", "Loja Fora Da Configuracao")]

    primeira = _sync_empresas(db, simulado)
    segunda = _sync_empresas(db, simulado)

    empresas = db.scalars(
        select(Empresa).where(Empresa.ambiente == AMBIENTE).order_by(Empresa.id)
    ).all()
    assert [e.id_erp for e in empresas] == [*EMPRESAS, "9"]
    assert {e.id_erp: e.ativo for e in empresas}["9"] is False
    assert all(e.ativo for e in empresas if e.id_erp in EMPRESAS)
    assert empresas[0].codigo == "1" and empresas[0].bairro == "Bairro Ficticio"

    um = _execucao(db, primeira.sincronizacao_id)
    assert (um.status, um.registros_criados, um.empresas_processadas) == ("sucesso", 7, 7)
    dois = _execucao(db, segunda.sincronizacao_id)
    assert (dois.status, dois.registros_criados, dois.registros_atualizados) == ("sucesso", 0, 0)


def test_empresa_alterada_no_erp_e_atualizada(db):
    simulado = ErpApiSimulado()
    simulado.lojas = _lojas("1")
    _sync_empresas(db, simulado)

    simulado.lojas = [loja("1", "Nome Novo", "Bairro Novo")]
    resultado = _sync_empresas(db, simulado)

    empresa = db.scalar(select(Empresa).where(Empresa.ambiente == AMBIENTE))
    db.refresh(empresa)
    assert (empresa.nome, empresa.bairro) == ("Nome Novo", "Bairro Novo")
    assert _execucao(db, resultado.sincronizacao_id).registros_atualizados == 1


def test_loja_invalida_e_ignorada_e_execucao_fica_parcial(db):
    simulado = ErpApiSimulado()
    simulado.lojas = [*_lojas("1"), {"nomefantasia": "sem id"}]

    resultado = _sync_empresas(db, simulado)

    assert resultado.status == "parcial"
    execucao = _execucao(db, resultado.sincronizacao_id)
    assert (execucao.registros_criados, execucao.registros_ignorados) == (1, 1)
    assert [e.tipo_erro for e in _erros(db, [execucao.id])] == ["RegistroInvalido"]


def test_estoque_percorre_todas_as_paginas_de_todas_as_empresas(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])

    simulado.com_estoque(
        "1",
        [saldo("1", str(900100 + i), "1", "1") for i in range(100)],
        [saldo("1", str(900200 + i), "1", "1") for i in range(100)],
        [saldo("1", "900001", "1", "1")],
    )

    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "sucesso"
    assert simulado.chamadas_estoque("1") == [("1", 1), ("1", 2), ("1", 3)]
    esperadas = sorted(["1"] * 3 + list(EMPRESAS[1:]))
    assert sorted(e for e, _ in simulado.chamadas_estoque()) == esperadas
    pai = _execucao(db, resultado.sincronizacao_id)
    assert (pai.empresas_processadas, pai.paginas_processadas, pai.registros_consultados) == (
        6,
        8,
        206,
    )
    assert pai.registros_gravados == 206
    filhas = _filhas(db, pai.id)
    assert set(filhas) == set(EMPRESAS)
    assert filhas["1"].paginas_processadas == 3
    assert all(f.status == "sucesso" for f in filhas.values())


def test_estoque_salvo_por_empresa_local_lote_e_consolidado_soma_so_as_configuradas(
    com_empresas,
):
    db = com_empresas

    simulado_lojas = ErpApiSimulado()
    simulado_lojas.lojas = _lojas(*EMPRESAS, "7")
    _sync_empresas(db, simulado_lojas)

    simulado = ErpApiSimulado()
    simulado.com_estoque(
        "1",
        [
            saldo("1", "900001", "10", "8", reservado="2", local="1"),
            saldo("1", "900001", "5", "5", local="2"),
            saldo("1", "900001", "1.5", "1.5", local="2", lote="L-A"),
            saldo("1", "900002", "0", "0"),
        ],
    )
    simulado.com_estoque("2", [saldo("2", "900001", "4", "3", reservado="1")])
    for empresa in ("3", "4", "5", "6"):
        simulado.com_estoque(empresa, [saldo(empresa, "900003", "1", "1")])
    simulado.com_estoque("7", [saldo("7", "900001", "1000", "1000")])

    _sync_estoque(db, simulado, empresas=("7",))
    _sync_estoque(db, simulado)

    linhas = _linhas(db, ativo=True)
    detalhe = {
        (x.empresa.id_erp, x.id_produto, x.id_local_estoque, x.descricao_lote): x for x in linhas
    }
    assert ("1", "900001", "2", "L-A") in detalhe
    assert detalhe[("1", "900001", "2", "L-A")].saldo_atual == dec("1.500")
    assert detalhe[("1", "900001", "1", "")].saldo_reservado == dec("2.000")

    total = _consolidado(db, "900001")
    assert total.saldo_atual_total == dec("20.500")
    assert total.saldo_disponivel_total == dec("17.500")
    assert total.saldo_reservado_total == dec("3.000")
    assert total.empresas_com_estoque == 2
    assert _consolidado(db, "900002").empresas_com_estoque == 0
    assert _consolidado(db, "900003").saldo_atual_total == dec("4.000")


def test_403_numa_filial_nao_derruba_as_outras_e_preserva_o_estoque_dela(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    _sync_estoque(db, simulado)

    simulado.com_estoque("1", [saldo("1", "900001", "9", "9")])
    simulado.falhar("3", 1, httpx2.Response(403, json={"error": "servico nao liberado"}))
    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "parcial"
    filhas = _filhas(db, resultado.sincronizacao_id)
    assert filhas["3"].status == "erro"
    assert "ErpApiAcessoNegadoError" in filhas["3"].mensagem_erro
    assert all(filhas[e].status == "sucesso" for e in EMPRESAS if e != "3")

    assert _consolidado(db, "900001").saldo_atual_total == dec("14.000")
    assert len(_linhas(db, ativo=True)) == 6

    erro = _erros(db, [filhas["3"].id])[0]
    assert (erro.status_http, erro.id_erp_empresa, erro.tipo_erro) == (
        403,
        "3",
        "ErpApiAcessoNegadoError",
    )
    assert erro.endpoint == "/erpcore-service/produtos_saldo_estoque_empresa"

    assert "page=1, clausulas=[idempresa IGUAL 3, dtalteracao MAIOR_IGUAL" in erro.mensagem


def test_5xx_transitorio_e_repetido_e_fica_registrado(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    simulado.falhar("2", 1, httpx2.Response(503), httpx2.Response(502))

    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "sucesso"
    assert simulado.chamadas_estoque("2") == [("2", 1)] * 3
    erros = _erros(db, _todos_os_ids(db, resultado.sincronizacao_id))
    assert [(e.status_http, e.tentativa) for e in erros] == [(503, 1), (502, 2)]


def test_5xx_persistente_vira_erro_so_da_empresa(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    simulado.falhar("2", 1, *[httpx2.Response(500)] * 3)

    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "parcial"
    assert _filhas(db, resultado.sincronizacao_id)["2"].status == "erro"


def test_401_renova_token_uma_vez_e_segue(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    simulado.falhar("1", 1, httpx2.Response(401))

    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "sucesso"
    pedidos_token = [r for r in simulado.requisicoes if r.url.path == "/teste/token"]
    assert len(pedidos_token) == 2


def test_falha_de_autenticacao_interrompe_e_registra(com_empresas, caplog):
    db = com_empresas
    simulado = ErpApiSimulado()
    simulado.falhas_token = [httpx2.Response(401, json={"error": "invalid_grant"})]

    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "erro"
    assert "interrompida" in resultado.mensagem
    assert _filhas(db, resultado.sincronizacao_id) == {}
    assert simulado.chamadas_estoque() == []
    erros = _erros(db, [resultado.sincronizacao_id])
    assert [(e.tipo_erro, e.status_http) for e in erros] == [("ErpApiNaoAutorizadoError", 401)]


def test_erpapi_fora_do_ar_interrompe_no_meio(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    simulado.falhar("2", 1, *[httpx2.ConnectError("recusada")] * 3)

    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "erro"
    filhas = _filhas(db, resultado.sincronizacao_id)
    assert (filhas["1"].status, filhas["2"].status) == ("sucesso", "erro")
    assert "3" not in filhas

    assert _consolidado(db, "900001").saldo_atual_total == dec("1.000")


def test_registro_de_outra_empresa_e_descartado_e_nada_e_desativado(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    _sync_estoque(db, simulado)

    simulado.com_estoque("1", [saldo("1", "900009", "1", "1"), saldo("2", "900001", "50", "50")])
    resultado = _sync_estoque(db, simulado, completa=True)
    _sync_estoque(db, simulado, completa=True)

    filha = _filhas(db, resultado.sincronizacao_id)["1"]
    assert filha.status == "parcial"
    assert filha.registros_ignorados == 1
    assert "ausencias nao foram contadas" in filha.mensagem_erro
    assert _linhas(db, ativo=False) == []
    assert _consolidado(db, "900001").saldo_atual_total == dec("6.000")


def test_resposta_sem_registro_valido_mantem_o_estoque(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])
    _sync_estoque(db, simulado)

    simulado.com_estoque("1", [{"campo_inesperado": 1}])
    resultado = _sync_estoque(db, simulado, completa=True)

    filha = _filhas(db, resultado.sincronizacao_id)["1"]
    assert filha.status == "erro"
    assert "estoque anterior mantido" in filha.mensagem_erro
    assert len(_linhas(db, ativo=True)) == 6


def test_empresa_nao_cadastrada_vira_erro_registrado(db):
    simulado = ErpApiSimulado()
    simulado.lojas = _lojas("1")
    _sync_empresas(db, simulado, empresas=("1",))
    simulado.com_estoque("1", [saldo("1", "900001", "1", "1")])

    resultado = _sync_estoque(db, simulado, empresas=("1", "2"))

    assert resultado.status == "parcial"
    assert "empresas nao cadastradas: 2" in resultado.mensagem
    erros = _erros(db, [resultado.sincronizacao_id])
    assert [(e.tipo_erro, e.id_erp_empresa) for e in erros] == [("EmpresaNaoCadastrada", "2")]


def test_token_e_segredos_nao_aparecem_em_log_nem_no_banco(com_empresas, caplog):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])

    simulado.falhar("2", 1, httpx2.Response(400, text=f"token recusado: {TOKEN}"))

    with caplog.at_level(logging.DEBUG):
        resultado = _sync_estoque(db, simulado)

    mensagens = [e.mensagem for e in _erros(db, _todos_os_ids(db, resultado.sincronizacao_id))]
    mensagens += [s.mensagem_erro or "" for s in _filhas(db, resultado.sincronizacao_id).values()]
    mensagens.append(_execucao(db, resultado.sincronizacao_id).mensagem_erro or "")
    for texto in [caplog.text, *mensagens]:
        for segredo in (TOKEN, SENHA, CLIENT_SECRET):
            assert segredo not in texto
    assert any("pedido: page=1" in m for m in mensagens)


def _todas_com(simulado):
    for empresa in EMPRESAS:
        simulado.com_estoque(empresa, [saldo(empresa, "900001", "1", "1")])


def test_incremental_le_so_o_que_mudou_e_as_reservas(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    simulado.com_estoque(
        "1",
        [
            saldo("1", "900001", "10", "10", dtalteracao="2026-10-07 08:00:00"),
            saldo("1", "900002", "5", "5", dtalteracao="2026-09-01 10:00:00"),
            saldo("1", "900003", "4", "4", dtalteracao="2026-09-01 10:00:00"),
        ],
    )
    _sync_estoque(db, simulado)

    simulado.requisicoes.clear()
    simulado.com_estoque(
        "1",
        [
            saldo("1", "900001", "7", "7", dtalteracao="2026-10-07 09:15:00"),
            saldo("1", "900002", "99", "99", dtalteracao="2026-09-01 10:00:00"),
            saldo("1", "900003", "4", "1", reservado="3", dtalteracao="2026-09-01 10:00:00"),
        ],
    )
    resultado = _sync_estoque(db, simulado)

    assert resultado.status == "sucesso"
    filtros = {f for _, _, f in simulado.consultas_estoque("1")}

    assert filtros == {
        (("dtalteracao", "MAIOR_IGUAL", "2026-10-07 07:50:00"),),
        (("qtdsaldoreserva", "MAIOR", "0"),),
    }
    assert _consolidado(db, "900001").saldo_atual_total == dec("12.000")
    assert _consolidado(db, "900002").saldo_atual_total == dec("5.000")
    reservado = _consolidado(db, "900003")
    assert (reservado.saldo_disponivel_total, reservado.saldo_reservado_total) == (
        dec("1.000"),
        dec("3.000"),
    )
    filha = _filhas(db, resultado.sincronizacao_id)["1"]
    assert (filha.status, filha.registros_ignorados) == ("sucesso", 0)


def test_reserva_liberada_sem_mudar_saldo_e_reconsultada_por_produto(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    antiga = {"sub": "7", "local": "3", "dtalteracao": "2026-08-01 10:00:00"}
    recente = saldo("1", "900001", "1", "1", dtalteracao="2026-10-07 10:00:00")
    simulado.com_estoque("1", [recente, saldo("1", "900005", "10", "8", reservado="2", **antiga)])
    _sync_estoque(db, simulado)

    simulado.com_estoque("1", [recente, saldo("1", "900005", "10", "10", reservado="0", **antiga)])
    simulado.requisicoes.clear()
    _sync_estoque(db, simulado)

    por_produto = [f for _, _, f in simulado.consultas_estoque("1") if f and f[0][0] == "idproduto"]
    assert por_produto == [
        (("idproduto", "IGUAL", "900005"), ("idsubproduto", "IGUAL", "7")),
    ]
    total = _consolidado(db, "900005", sub="7")
    assert (total.saldo_disponivel_total, total.saldo_reservado_total) == (
        dec("10.000"),
        dec("0.000"),
    )


def test_incremental_nunca_desativa(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    _sync_estoque(db, simulado)

    simulado.com_estoque("1", [])
    _sync_estoque(db, simulado)

    assert _linhas(db, ativo=False) == []
    assert _consolidado(db, "900001").saldo_atual_total == dec("6.000")


def test_leitura_completa_so_desativa_na_segunda_ausencia_seguida(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    for empresa in EMPRESAS:
        simulado.com_estoque(
            empresa, [saldo(empresa, "900001", "2", "2"), saldo(empresa, "900002", "3", "3")]
        )
    _sync_estoque(db, simulado, completa=True)
    _sync_estoque(db, simulado, completa=True)
    assert len(_linhas(db)) == 12

    simulado.com_estoque("1", [saldo("1", "900001", "2", "2")])
    primeira = _sync_estoque(db, simulado, completa=True)
    linha = next(x for x in _linhas(db) if (x.empresa.id_erp, x.id_produto) == ("1", "900002"))
    assert (linha.ativo, linha.ausencias_leitura_completa) == (True, 1)
    assert _consolidado(db, "900002").saldo_atual_total == dec("18.000")
    assert _filhas(db, primeira.sincronizacao_id)["1"].status == "sucesso"

    _sync_estoque(db, simulado, completa=True)
    inativas = _linhas(db, ativo=False)
    assert [(x.empresa.id_erp, x.id_produto) for x in inativas] == [("1", "900002")]
    assert inativas[0].removido_em is not None
    assert len(_linhas(db)) == 12
    assert _consolidado(db, "900002").saldo_atual_total == dec("15.000")

    simulado.com_estoque("1", [saldo("1", "900001", "2", "2"), saldo("1", "900002", "1", "1")])
    _sync_estoque(db, simulado, completa=True)
    assert _linhas(db, ativo=False) == []
    assert all(x.ausencias_leitura_completa == 0 for x in _linhas(db))


def test_ausencia_volta_a_zero_se_a_linha_aparece_entre_duas_completas(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    com_as_duas = [saldo("1", "900001", "1", "1"), saldo("1", "900002", "1", "1")]
    so_uma = [saldo("1", "900001", "1", "1")]
    simulado.com_estoque("1", com_as_duas)
    _sync_estoque(db, simulado, completa=True)

    simulado.com_estoque("1", so_uma)
    _sync_estoque(db, simulado, completa=True)
    simulado.com_estoque("1", com_as_duas)
    _sync_estoque(db, simulado, completa=True)
    simulado.com_estoque("1", so_uma)
    _sync_estoque(db, simulado, completa=True)

    assert _linhas(db, ativo=False) == []


def test_completa_conta_duplicados_e_incremental_nao(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    linha = saldo("1", "900001", "1", "1")

    simulado.com_estoque("1", [linha], [linha])

    completa = _sync_estoque(db, simulado, completa=True)
    assert _filhas(db, completa.sincronizacao_id)["1"].registros_ignorados == 1

    simulado.com_estoque("1", [saldo("1", "900001", "1", "0", reservado="1")])
    incremental = _sync_estoque(db, simulado)
    assert _filhas(db, incremental.sincronizacao_id)["1"].status == "sucesso"


def test_completa_com_linha_repetida_nao_conta_ausencias(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    fica = saldo("1", "900001", "1", "1")
    some = saldo("1", "900002", "1", "1")
    simulado.com_estoque("1", [fica, some])
    _sync_estoque(db, simulado, completa=True)

    simulado.com_estoque("1", [fica], [fica])
    for _ in range(2):
        resultado = _sync_estoque(db, simulado, completa=True)

    filha = _filhas(db, resultado.sincronizacao_id)["1"]
    assert "ausencias nao foram contadas" in filha.mensagem_erro
    assert _linhas(db, ativo=False) == []


def test_fuso_do_erp_e_respeitado_na_data_gravada(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    simulado.com_estoque("1", [saldo("1", "900001", "1", "1", dtalteracao="2026-10-07 13:00:00")])

    _sync_estoque(db, simulado)

    linha = next(x for x in _linhas(db) if x.empresa.id_erp == "1")

    assert linha.data_alteracao_erp == datetime(2026, 10, 7, 17, 0, tzinfo=UTC)
    assert linha.inativo_erp is False


def test_data_de_alteracao_no_futuro_nao_adianta_o_cursor_incremental(com_empresas):
    db = com_empresas
    simulado = ErpApiSimulado()
    _todas_com(simulado)
    simulado.com_estoque(
        "1",
        [
            saldo("1", "900001", "10", "10", dtalteracao="2026-10-07 08:00:00"),
            saldo("1", "900002", "5", "5", dtalteracao="2027-06-01 08:00:00"),
        ],
    )
    _sync_estoque(db, simulado)
    simulado.requisicoes.clear()

    _sync_estoque(db, simulado)

    desde = {
        v for _, _, f in simulado.consultas_estoque("1") for c, _, v in f if c == "dtalteracao"
    }
    assert len(desde) == 1
    assert desde.pop() < "2027"
