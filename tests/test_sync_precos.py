import httpx2
import pytest
from sqlalchemy import select

from app.database.models import (
    Empresa,
    IntegracaoErro,
    PrecoProdutoEmpresa,
    Produto,
    Sincronizacao,
)
from app.erp.servicos import ROTA_CAD_PRODUTOS, ROTA_PRECOS_CUSTOS
from app.sync.empresas import sincronizar_empresas
from app.sync.precos import sincronizar_precos
from tests.sync_fakes import (
    ErpApiSimulado,
    dec,
    fabrica_de,
    loja,
    politica,
    preco,
    produto,
    servicos_para,
)

pytestmark = pytest.mark.integration

AMBIENTE = "teste-sync"
EMPRESAS = ("1", "2")


@pytest.fixture(autouse=True)
def _sem_dados_reais(db_vazio):
    pass


@pytest.fixture
def com_empresas(db):
    simulado = ErpApiSimulado()
    simulado.lojas = [loja(i, f"Loja Ficticia {i}") for i in EMPRESAS]
    sincronizar_empresas(
        fabrica_de(db),
        servicos_para(simulado),
        ambiente=AMBIENTE,
        empresas_ativas=EMPRESAS,
        politica=politica()[0],
    )
    return db


def _sync(db, simulado, completa=False):
    return sincronizar_precos(
        fabrica_de(db),
        servicos_para(simulado),
        ambiente=AMBIENTE,
        empresas=EMPRESAS,
        politica=politica()[0],
        completa=completa,
    )


def _precos(db):
    db.expire_all()
    return {
        (p.empresa.id_erp, p.id_produto): p
        for p in db.scalars(
            select(PrecoProdutoEmpresa).join(Empresa).where(Empresa.ambiente == AMBIENTE)
        )
    }


def _produtos(db):
    db.expire_all()
    return {p.id_produto: p for p in db.scalars(select(Produto))}


def _filhas(db, pai_id):
    db.expire_all()
    return {
        (s.empresa.id_erp if s.empresa else "produtos"): s
        for s in db.scalars(
            select(Sincronizacao).where(Sincronizacao.sincronizacao_pai_id == pai_id)
        )
    }


def _simulado_basico():
    return (
        ErpApiSimulado()
        .com_produtos([produto("900001", "CAFE FICTICIO 500G"), produto("900002")])
        .com_precos(
            "1", [preco("1", "900001", varejo=12.9, custo=8.123456)], [preco("1", "900002")]
        )
        .com_precos("2", [preco("2", "900001", varejo=13.5, custo=8.5)])
    )


def test_primeira_execucao_le_tudo_e_grava_produtos_e_precos(com_empresas):
    db = com_empresas
    simulado = _simulado_basico()

    resultado = _sync(db, simulado)

    assert resultado.status == "sucesso"

    assert all(
        f[0] != "dtalteracao"
        for _, filtros in simulado.consultas(ROTA_PRECOS_CUSTOS)
        for f in filtros
    )
    assert simulado.consultas(ROTA_CAD_PRODUTOS) == [(1, ())]

    produtos = _produtos(db)
    assert produtos["900001"].descricao == "CAFE FICTICIO 500G"
    assert produtos["900001"].secao == "SECAO FICTICIA"
    assert produtos["900001"].inativo_erp is False

    precos = _precos(db)
    assert set(precos) == {("1", "900001"), ("1", "900002"), ("2", "900001")}
    p = precos[("1", "900001")]
    assert p.preco_varejo == dec("12.900000")
    assert p.custo_gerencial == dec("8.123456")
    assert p.custo_reposicao == dec("8.123456")
    assert p.inicio_promocao_varejo is None
    assert precos[("2", "900001")].preco_varejo == dec("13.500000")

    filhas = _filhas(db, resultado.sincronizacao_id)
    assert set(filhas) == {"produtos", "1", "2"}
    assert filhas["1"].registros_criados == 2 and filhas["1"].paginas_processadas == 2
    assert filhas["produtos"].empresa_id is None


def test_segunda_execucao_e_incremental_pela_data_de_alteracao(com_empresas):
    db = com_empresas
    simulado = _simulado_basico()
    _sync(db, simulado)

    simulado.com_precos(
        "1",
        [preco("1", "900001", varejo=14.0, custo=9.0, dtalteracao="2026-10-02 10:00:00")],
        [preco("1", "900002")],
    )
    simulado.requisicoes.clear()
    resultado = _sync(db, simulado)

    assert resultado.status == "sucesso"

    consultas = {f[0][2]: f[1:] for _, f in simulado.consultas(ROTA_PRECOS_CUSTOS)}
    assert consultas["1"] == (("dtalteracao", "MAIOR_IGUAL", "2026-10-01 08:20:00"),)
    assert simulado.consultas(ROTA_CAD_PRODUTOS) == [
        (1, (("dtalteracao", "MAIOR_IGUAL", "2026-10-01 08:20:00"),))
    ]

    precos = _precos(db)
    assert precos[("1", "900001")].preco_varejo == dec("14.000000")
    assert precos[("1", "900001")].custo_gerencial == dec("9.000000")

    assert len(precos) == 3


def test_repetir_nao_duplica(com_empresas):
    db = com_empresas
    simulado = _simulado_basico()
    _sync(db, simulado)
    resultado = _sync(db, simulado, completa=True)

    filhas = _filhas(db, resultado.sincronizacao_id)
    assert filhas["1"].registros_criados == 0 and filhas["1"].registros_atualizados == 2
    assert len(_precos(db)) == 3 and len(_produtos(db)) == 2


def test_leitura_completa_ignora_a_data(com_empresas):
    db = com_empresas
    simulado = _simulado_basico()
    _sync(db, simulado)
    simulado.requisicoes.clear()

    resultado = _sync(db, simulado, completa=True)

    db.expire_all()
    assert db.get(Sincronizacao, resultado.sincronizacao_id).tipo == "precos_completo"
    assert all(len(f) == 1 for _, f in simulado.consultas(ROTA_PRECOS_CUSTOS))
    assert simulado.consultas(ROTA_CAD_PRODUTOS) == [(1, ())]


def test_registro_de_outra_empresa_e_ignorado(com_empresas):
    db = com_empresas
    simulado = _simulado_basico().com_precos("2", [preco("2", "900001"), preco("1", "900009")])

    resultado = _sync(db, simulado)

    assert resultado.status == "parcial"
    assert ("1", "900009") not in _precos(db)
    filhas = _filhas(db, resultado.sincronizacao_id)
    assert filhas["2"].status == "parcial" and filhas["2"].registros_ignorados == 1
    tipos = db.scalars(
        select(IntegracaoErro.tipo_erro).where(IntegracaoErro.sincronizacao_id == filhas["2"].id)
    ).all()
    assert tipos == ["RegistroDeOutraEmpresa"]


def test_acesso_negado_numa_empresa_nao_derruba_as_outras(com_empresas):
    db = com_empresas
    simulado = _simulado_basico().falhar("2", 1, httpx2.Response(403, json={"erro": "x"}))

    resultado = _sync(db, simulado)

    assert resultado.status == "parcial"
    filhas = _filhas(db, resultado.sincronizacao_id)
    assert filhas["2"].status == "erro"
    assert filhas["1"].status == "sucesso" and filhas["produtos"].status == "sucesso"
    assert set(_precos(db)) == {("1", "900001"), ("1", "900002")}


def test_falha_geral_interrompe(com_empresas):
    db = com_empresas
    simulado = _simulado_basico().falhar(
        "produtos", 1, *(httpx2.ConnectError("sem rota") for _ in range(3))
    )

    resultado = _sync(db, simulado)

    assert resultado.status == "erro"
    assert "interrompida" in (resultado.mensagem or "")
    assert _precos(db) == {}


def test_data_de_alteracao_no_futuro_nao_adianta_o_cursor_incremental(com_empresas):
    db = com_empresas
    simulado = (
        ErpApiSimulado()
        .com_produtos([produto("900001")])
        .com_precos("1", [preco("1", "900001", dtalteracao="2027-06-01 08:00:00")])
        .com_precos("2", [preco("2", "900001")])
    )
    _sync(db, simulado)
    simulado.requisicoes.clear()

    _sync(db, simulado)

    consultas = {f[0][2]: f[1:] for _, f in simulado.consultas(ROTA_PRECOS_CUSTOS)}
    ((campo, _, desde),) = consultas["1"]
    assert campo == "dtalteracao" and desde < "2027"
