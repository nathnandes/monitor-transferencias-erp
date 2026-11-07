from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    UniqueConstraint,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from app.database.base import Base
from app.database.models import (
    Empresa,
    Evento,
    Log,
    Sincronizacao,
    Transferencia,
    TransferenciaItem,
)

RAIZ = Path(__file__).resolve().parent.parent


def _unicas(tabela: str) -> dict[str, list[str]]:
    return {
        c.name: [col.name for col in c.columns]
        for c in Base.metadata.tables[tabela].constraints
        if isinstance(c, UniqueConstraint)
    }


def test_chaves_de_idempotencia_declaradas():
    assert _unicas("empresas")["uq_empresas_id_erp_ambiente"] == ["id_erp", "ambiente"]
    assert _unicas("transferencias")["uq_transferencias_origem_id_erp"] == [
        "empresa_origem_id",
        "id_erp",
    ]


def test_itens_nao_tem_chave_unica_por_produto():
    assert _unicas("transferencias_itens") == {}


COLUNAS_REGRAVADAS = [
    ("estoque_consolidado", "id"),
    ("movimentos_estoque", "id"),
    ("vendas", "id"),
    ("vendas_itens", "id"),
    ("vendas_itens", "venda_id"),
    ("devolucoes", "id"),
    ("transferencias_itens", "id"),
]


@pytest.mark.parametrize(("tabela", "coluna"), COLUNAS_REGRAVADAS)
def test_ids_das_tabelas_regravadas_sao_bigint(tabela, coluna):
    assert isinstance(Base.metadata.tables[tabela].c[coluna].type, BigInteger)


def _indices(tabela: str) -> dict[str, list[str]]:
    return {
        i.name: [c.name for c in i.columns]
        for i in Base.metadata.tables[tabela].indexes
        if i.name is not None
    }


def test_indices_dos_filtros_do_livro_das_vendas_e_das_transferencias():
    movimentos = _indices("movimentos_estoque")

    assert movimentos["ix_movimentos_estoque_coi_dia_empresa"] == ["coi", "dia", "empresa_id"]

    assert movimentos["ix_movimentos_estoque_subproduto"] == ["id_subproduto"]

    assert _indices("vendas")["ix_vendas_id_vendedor"] == ["id_vendedor"]
    assert _indices("transferencias")["ix_transferencias_status_data_criacao"] == [
        "status",
        "data_criacao",
    ]


def test_subproduto_do_livro_nunca_e_nulo():
    assert Base.metadata.tables["movimentos_estoque"].c["id_subproduto"].nullable is False


def test_status_da_transferencia_e_sempre_maiusculo():
    checks = {
        c.name: str(c.sqltext)
        for c in Base.metadata.tables["transferencias"].constraints
        if isinstance(c, CheckConstraint)
    }
    assert checks["ck_transferencias_status_maiusculo"] == "status = upper(status)"


def test_uma_unica_head_nas_migrations():
    heads = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_heads()
    assert len(heads) == 1, heads


def test_raw_data_e_payload_sao_jsonb():
    for tabela, coluna in [
        ("transferencias", "raw_data"),
        ("transferencias_itens", "raw_data"),
        ("eventos", "payload"),
        ("logs", "payload"),
    ]:
        assert isinstance(Base.metadata.tables[tabela].c[coluna].type, JSONB)


integration = pytest.mark.integration


def _viola(db, constraint: str | None, *objetos) -> None:
    with pytest.raises(IntegrityError) as erro:
        with db.begin_nested():
            db.add_all(objetos)
            db.flush()
    if constraint is not None:
        assert erro.value.orig.diag.constraint_name == constraint


def _empresa(codigo: str, id_erp: str | None = None, ambiente: str = "producao"):
    return Empresa(codigo=codigo, nome=f"Empresa {codigo}", id_erp=id_erp, ambiente=ambiente)


def _transferencia_por_ids(id_erp: str, origem, destino, **campos) -> Transferencia:
    return Transferencia(
        id_erp=id_erp, empresa_origem_id=origem.id, empresa_destino_id=destino.id, **campos
    )


@pytest.fixture
def empresas(db):
    origem, destino = _empresa("T01", "900001"), _empresa("T02", "900002")
    db.add_all([origem, destino])
    db.flush()
    return origem, destino


@integration
def test_banco_esta_na_head_das_migrations(engine):
    head = ScriptDirectory.from_config(Config(str(RAIZ / "alembic.ini"))).get_current_head()
    with engine.connect() as conexao:
        atual = MigrationContext.configure(conexao).get_current_revision()

    assert atual == head, "banco desatualizado — rode: python -m alembic upgrade head"


@integration
def test_models_e_migrations_nao_divergem(engine):
    with engine.connect() as conexao:
        contexto = MigrationContext.configure(conexao, opts={"compare_type": True})
        diferencas = compare_metadata(contexto, Base.metadata)

    assert diferencas == []


@integration
def test_sequencias_das_tabelas_regravadas_vao_alem_do_int4(engine):
    tabelas = sorted({t for t, c in COLUNAS_REGRAVADAS if c == "id"})
    with engine.connect() as conexao:
        maximos = dict(
            conexao.execute(
                text(
                    "SELECT t, s.max_value FROM unnest(CAST(:tabelas AS text[])) AS t"
                    " JOIN pg_sequences s"
                    " ON s.schemaname || '.' || s.sequencename"
                    " = pg_get_serial_sequence(t, 'id')"
                ),
                {"tabelas": tabelas},
            ).all()
        )

    assert maximos == dict.fromkeys(tabelas, 2**63 - 1)


@integration
def test_empresa_id_erp_duplicado_no_mesmo_ambiente_e_rejeitado(db):
    db.add(_empresa("T01", "900001"))
    db.flush()

    _viola(db, "uq_empresas_id_erp_ambiente", _empresa("T02", "900001"))


@integration
def test_empresa_mesmo_id_erp_em_ambientes_diferentes_e_aceito(db):
    db.add_all([_empresa("T01", "900001", "producao"), _empresa("T02", "900001", "homologacao")])
    db.flush()


@integration
def test_empresas_sem_id_erp_nao_conflitam(db):
    db.add_all([_empresa("T01"), _empresa("T02")])
    db.flush()


@integration
def test_empresa_codigo_duplicado_e_rejeitado(db):
    db.add(_empresa("T01"))
    db.flush()

    _viola(db, "ix_empresas_codigo", _empresa("T01"))


@integration
def test_empresa_com_transferencias_nao_pode_ser_apagada(db, empresas):
    origem, destino = empresas
    db.add(Transferencia(id_erp="1", empresa_origem=origem, empresa_destino=destino))
    db.flush()

    with pytest.raises(IntegrityError) as erro:
        with db.begin_nested():
            db.delete(origem)
            db.flush()
    assert erro.value.orig.diag.constraint_name == "transferencias_empresa_origem_id_fkey"


@integration
def test_transferencia_id_erp_duplicado_na_mesma_origem_e_rejeitado(db, empresas):
    origem, destino = empresas
    db.add(Transferencia(id_erp="458921", empresa_origem=origem, empresa_destino=destino))
    db.flush()

    _viola(
        db,
        "uq_transferencias_origem_id_erp",
        _transferencia_por_ids("458921", origem, destino),
    )


@integration
def test_transferencia_mesmo_id_erp_em_origens_diferentes_e_aceito(db, empresas):
    a, b = empresas
    db.add_all(
        [
            Transferencia(id_erp="1", empresa_origem=a, empresa_destino=b),
            Transferencia(id_erp="1", empresa_origem=b, empresa_destino=a),
        ]
    )
    db.flush()


@integration
def test_transferencia_exige_empresa_existente(db):
    _viola(
        db,
        "transferencias_empresa_origem_id_fkey",
        Transferencia(id_erp="1", empresa_origem_id=-1, empresa_destino_id=-1),
    )


@integration
def test_transferencia_quantidade_itens_negativa_e_rejeitada(db, empresas):
    origem, destino = empresas
    _viola(
        db,
        "ck_transferencias_quantidade_itens",
        _transferencia_por_ids("1", origem, destino, quantidade_itens=-1),
    )


@integration
def test_transferencia_relacionamentos_e_raw_data(db, empresas):
    origem, destino = empresas
    bruto = {"qualquer": ["formato", 1, None], "aninhado": {"ok": True}}
    transferencia = Transferencia(
        id_erp="458921",
        empresa_origem=origem,
        empresa_destino=destino,
        status="PENDENTE",
        data_criacao=datetime(2026, 9, 25, 12, tzinfo=UTC),
        quantidade_itens=2,
        raw_data=bruto,
        itens=[
            TransferenciaItem(id_produto_erp="P1", quantidade_solicitada=Decimal("1.5")),
            TransferenciaItem(id_produto_erp="P1", quantidade_solicitada=Decimal("2")),
        ],
    )
    db.add(transferencia)
    db.flush()
    db.expire_all()

    lida = db.get(Transferencia, transferencia.id)
    assert lida.empresa_origem.codigo == "T01"
    assert lida.empresa_destino.codigo == "T02"
    assert lida.raw_data == bruto
    assert [i.quantidade_solicitada for i in lida.itens] == [Decimal("1.5"), Decimal("2")]
    assert lida in origem.transferencias_origem
    assert lida in destino.transferencias_destino
    assert lida.created_at is not None and lida.updated_at is not None


@integration
def test_raw_data_padrao_e_objeto_vazio(db, empresas):
    origem, destino = empresas
    transferencia = Transferencia(id_erp="1", empresa_origem=origem, empresa_destino=destino)
    db.add(transferencia)
    db.flush()

    assert transferencia.raw_data == {}


@integration
def test_itens_sao_apagados_em_cascata_pelo_banco(db, empresas):
    origem, destino = empresas
    transferencia = Transferencia(
        id_erp="1",
        empresa_origem=origem,
        empresa_destino=destino,
        itens=[TransferenciaItem(id_produto_erp="P1"), TransferenciaItem(id_produto_erp="P2")],
    )
    db.add(transferencia)
    db.flush()

    db.execute(delete(Transferencia).where(Transferencia.id == transferencia.id))
    restantes = db.scalar(
        select(func.count())
        .select_from(TransferenciaItem)
        .where(TransferenciaItem.transferencia_id == transferencia.id)
    )
    assert restantes == 0


@integration
def test_item_exige_transferencia_existente(db):
    _viola(
        db,
        "transferencias_itens_transferencia_id_fkey",
        TransferenciaItem(transferencia_id=-1, id_produto_erp="P1"),
    )


@integration
def test_item_exige_id_produto_erp(db, empresas):
    origem, destino = empresas
    transferencia = Transferencia(id_erp="1", empresa_origem=origem, empresa_destino=destino)
    db.add(transferencia)
    db.flush()

    _viola(db, None, TransferenciaItem(transferencia_id=transferencia.id, id_produto_erp=None))


@integration
def test_sincronizacao_defaults(db):
    sincronizacao = Sincronizacao(tipo="transferencias")
    db.add(sincronizacao)
    db.flush()
    db.refresh(sincronizacao)

    assert sincronizacao.status == "em_andamento"
    assert sincronizacao.inicio is not None
    assert sincronizacao.registros_ignorados == 0
    assert sincronizacao.empresa is None


@integration
def test_sincronizacao_status_invalido_e_rejeitado(db):
    _viola(db, "ck_sincronizacoes_status", Sincronizacao(tipo="x", status="ok"))


@integration
def test_sincronizacao_contador_negativo_e_rejeitado(db):
    _viola(db, "ck_sincronizacoes_contadores", Sincronizacao(tipo="x", registros_criados=-1))


@integration
def test_sincronizacao_fim_antes_do_inicio_e_rejeitado(db):
    agora = datetime.now(UTC)
    _viola(
        db,
        "ck_sincronizacoes_periodo",
        Sincronizacao(tipo="x", inicio=agora, fim=agora - timedelta(seconds=1)),
    )


@integration
def test_evento_relacionamentos_e_payload(db, empresas):
    origem, destino = empresas
    transferencia = Transferencia(id_erp="1", empresa_origem=origem, empresa_destino=destino)
    evento = Evento(
        tipo="transferencia_nova",
        origem="sync",
        severidade="INFO",
        referencia_externa="1",
        payload={"status_anterior": None},
        empresa=origem,
        transferencia=transferencia,
    )
    db.add(evento)
    db.flush()
    db.expire_all()

    lido = db.get(Evento, evento.id)
    assert lido.transferencia.id_erp == "1"
    assert lido.empresa.codigo == "T01"
    assert lido.payload == {"status_anterior": None}
    assert lido.data_evento is not None


@integration
def test_evento_severidade_invalida_e_rejeitada(db):
    _viola(db, "ck_eventos_severidade", Evento(tipo="x", origem="x", severidade="URGENTE"))


@integration
def test_log_grava_payload_e_data(db):
    log = Log(nivel="INFO", modulo="sync", evento="inicio", mensagem="ok", payload={"n": 1})
    db.add(log)
    db.flush()
    db.refresh(log)

    assert log.payload == {"n": 1}
    assert log.data is not None


@integration
def test_log_nivel_invalido_e_rejeitado(db):
    _viola(db, "ck_logs_nivel", Log(nivel="TRACE", modulo="x", evento="x", mensagem="x"))


@integration
def test_updated_at_muda_em_update_pelo_orm(db, empresas):
    origem, _ = empresas
    db.refresh(origem)
    antes = origem.updated_at

    db.execute(
        update(Empresa).where(Empresa.id == origem.id).values(updated_at=antes - timedelta(days=1))
    )
    db.refresh(origem)
    origem.nome = "Renomeada"
    db.flush()
    db.refresh(origem)

    assert origem.updated_at > antes - timedelta(days=1)


@integration
def test_check_do_tipo_do_livro_tem_as_categorias_do_catalogo(engine):
    import re

    from app.dominio.operacoes_estoque import CATEGORIAS

    with engine.connect() as conexao:
        definicao = conexao.execute(
            text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
                " JOIN pg_namespace n ON n.oid = c.connamespace"
                " WHERE c.conname = 'ck_movimentos_estoque_tipo' AND n.nspname = current_schema()"
            )
        ).scalar_one()

    assert set(re.findall(r"'([a-z_]+)'", definicao)) == set(CATEGORIAS)
