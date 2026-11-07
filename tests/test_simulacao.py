from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.database import simulacao
from app.database.models import (
    Empresa,
    Evento,
    Sincronizacao,
    Transferencia,
    TransferenciaItem,
)
from app.database.simulacao import (
    AMBIENTE_SIMULADO,
    EMPRESAS,
    EVENTOS,
    ORIGEM_EVENTO,
    PREFIXO_SIMULADO,
    TRANSFERENCIAS,
    AmbienteNaoPermitido,
    aplicar_seed,
    id_erp_transferencia,
    limpar_simulados,
    resumo_simulados,
    verificar_ambiente,
)

AGORA = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)

ESPERADO = {
    "empresas": 6,
    "transferencias": 36,
    "transferencias_por_status": {"ERRO": 5, "PENDENTE": 5, "PROCESSADA": 26},
    "itens": 109,
    "sincronizacoes": 12,
    "sincronizacoes_por_status": {"erro": 2, "parcial": 2, "sucesso": 8},
    "eventos": 21,
    "eventos_por_severidade": {"CRITICAL": 3, "ERROR": 7, "INFO": 4, "WARNING": 7},
    "vendas": 2160,
}

integration = pytest.mark.integration


def _settings(app_env: str = "", environment: str = "") -> Settings:
    return Settings(_env_file=None, app_env=app_env, environment=environment)


@pytest.mark.parametrize(
    ("app_env", "environment"),
    [
        ("production", ""),
        ("producao", ""),
        ("prod", ""),
        ("homologacao", ""),
        ("", "production"),
        ("development", "production"),
        ("production", "development"),
        ("", ""),
    ],
)
def test_seed_recusa_fora_de_development_ou_test(app_env, environment):
    with pytest.raises(AmbienteNaoPermitido):
        verificar_ambiente(_settings(app_env, environment))


@pytest.mark.parametrize(
    ("app_env", "environment"),
    [
        ("development", ""),
        ("test", ""),
        ("", "development"),
        ("", "test"),
        ("Development", "TEST"),
    ],
)
def test_seed_aceita_development_e_test(app_env, environment):
    verificar_ambiente(_settings(app_env, environment))


def test_mensagem_de_recusa_e_clara():
    with pytest.raises(AmbienteNaoPermitido, match=r"APP_ENV='production'.*development, test"):
        verificar_ambiente(_settings("production"))


@pytest.mark.parametrize("comando", ["seed", "limpar", "resumo"])
def test_cli_recusa_producao_antes_de_tocar_no_banco(monkeypatch, capsys, comando):
    monkeypatch.setattr(simulacao, "get_settings", lambda: _settings("production"))

    assert simulacao.main([comando]) == 2
    assert "RECUSADO" in capsys.readouterr().err


def test_environment_e_lido_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(AmbienteNaoPermitido, match="ENVIRONMENT"):
        verificar_ambiente(Settings(_env_file=None, app_env="development"))


def test_catalogo_de_empresas():
    assert EMPRESAS == ["01", "02", "03", "04", "05", "06"]


def test_catalogo_de_transferencias():
    assert len(TRANSFERENCIAS) >= 30
    assert {t.status for t in TRANSFERENCIAS} == {"PROCESSADA", "PENDENTE", "ERRO"}
    assert all(t.origem != t.destino for t in TRANSFERENCIAS)
    assert all(1 <= len(t.itens) <= 5 for t in TRANSFERENCIAS)

    idades = [t.criada_ha for t in TRANSFERENCIAS]
    assert max(idades) < timedelta(days=30)
    assert min(idades) < timedelta(hours=4)
    assert max(idades) > timedelta(days=25)


def test_catalogo_tem_divergencia_simulada():
    divergentes = [
        t
        for t in TRANSFERENCIAS
        if any(i.processada is not None and i.processada != i.solicitada for i in t.itens)
    ]
    assert divergentes and all(t.status == "PROCESSADA" for t in divergentes)


def test_catalogo_de_eventos_cobre_todas_as_severidades():
    assert {e.severidade for e in EVENTOS} == {"INFO", "WARNING", "ERROR", "CRITICAL"}
    numeros = {t.numero for t in TRANSFERENCIAS}
    assert all(e.transferencia in numeros for e in EVENTOS if e.transferencia is not None)


@pytest.fixture
def limpo(db):
    limpar_simulados(db)
    return db


def _chaves(db) -> tuple[dict[str, int], dict[str, int]]:
    empresas = dict(
        db.execute(
            select(Empresa.id_erp, Empresa.id).where(
                Empresa.ambiente == AMBIENTE_SIMULADO,
                Empresa.id_erp.startswith(PREFIXO_SIMULADO),
            )
        ).all()
    )
    transferencias = dict(
        db.execute(
            select(Transferencia.id_erp, Transferencia.id).where(
                Transferencia.id_erp.startswith(PREFIXO_SIMULADO)
            )
        ).all()
    )
    return empresas, transferencias


def _contagens(db) -> dict[str, int]:
    return {
        m.__tablename__: db.scalar(select(func.count()).select_from(m))
        for m in (Empresa, Transferencia, TransferenciaItem, Sincronizacao, Evento)
    }


@integration
def test_execucao_inicial_cria_o_conjunto_completo(limpo):
    resultado = aplicar_seed(limpo, AGORA)

    assert resultado.empresas_criadas == 6
    assert resultado.transferencias_criadas == 36
    assert resultado.itens == 109
    assert resumo_simulados(limpo) == ESPERADO

    empresa = limpo.scalar(select(Empresa).where(Empresa.codigo == "01"))
    assert empresa.nome == "Empresa Demonstração 01"
    assert empresa.ambiente == "development"
    assert empresa.id_erp == "DEMO-EMP-01"


@integration
def test_segunda_e_terceira_execucao_nao_duplicam(limpo):
    aplicar_seed(limpo, AGORA)
    chaves_antes = _chaves(limpo)
    contagens_antes = _contagens(limpo)

    segundo = aplicar_seed(limpo, AGORA)
    aplicar_seed(limpo, AGORA + timedelta(hours=3))

    assert (segundo.empresas_criadas, segundo.empresas_atualizadas) == (0, 6)
    assert (segundo.transferencias_criadas, segundo.transferencias_atualizadas) == (0, 36)
    assert resumo_simulados(limpo) == ESPERADO
    assert _contagens(limpo) == contagens_antes

    assert _chaves(limpo) == chaves_antes


@integration
def test_quantidade_itens_bate_com_os_itens_gravados(limpo):
    aplicar_seed(limpo, AGORA)
    aplicar_seed(limpo, AGORA)

    linhas = limpo.execute(
        select(
            Transferencia.id_erp,
            Transferencia.quantidade_itens,
            func.count(TransferenciaItem.id),
        )
        .outerjoin(TransferenciaItem)
        .where(Transferencia.id_erp.startswith(PREFIXO_SIMULADO))
        .group_by(Transferencia.id)
    ).all()

    assert len(linhas) == 36
    for id_erp, declarada, gravada in linhas:
        assert declarada == gravada, id_erp
        assert 1 <= gravada <= 5, id_erp

    for t in limpo.scalars(
        select(Transferencia).where(Transferencia.id_erp.startswith(PREFIXO_SIMULADO))
    ):
        assert len(t.raw_data["itens"]) == t.quantidade_itens


@integration
def test_seed_restaura_dados_simulados_alterados(limpo):
    aplicar_seed(limpo, AGORA)
    transferencia = limpo.scalar(
        select(Transferencia).where(Transferencia.id_erp == id_erp_transferencia(6))
    )
    transferencia.status = "ADULTERADO"
    transferencia.itens.pop()
    limpo.flush()

    aplicar_seed(limpo, AGORA)
    limpo.refresh(transferencia)

    assert transferencia.status == "ERRO"
    assert len(transferencia.itens) == transferencia.quantidade_itens == 4
    assert resumo_simulados(limpo) == ESPERADO


@integration
def test_hash_payload_e_estavel_entre_execucoes(limpo):
    aplicar_seed(limpo, AGORA)
    antes = dict(limpo.execute(select(Transferencia.id_erp, Transferencia.hash_payload)).all())

    aplicar_seed(limpo, AGORA + timedelta(days=2))
    depois = dict(limpo.execute(select(Transferencia.id_erp, Transferencia.hash_payload)).all())

    assert antes == depois


@integration
def test_datas_ficam_nos_ultimos_30_dias(limpo):
    aplicar_seed(limpo, AGORA)

    datas = limpo.scalars(
        select(Transferencia.data_criacao).where(Transferencia.id_erp.startswith(PREFIXO_SIMULADO))
    ).all()
    assert all(AGORA - timedelta(days=30) < d <= AGORA for d in datas)


@integration
def test_todos_os_registros_estao_marcados_como_ficticios(limpo):
    aplicar_seed(limpo, AGORA)

    empresas = limpo.scalars(
        select(Empresa).where(Empresa.id_erp.startswith(PREFIXO_SIMULADO))
    ).all()
    assert len(empresas) == 6
    assert all(e.nome.startswith("Empresa Demonstração ") for e in empresas)

    ids_empresas = {e.id for e in empresas}
    transferencias = limpo.scalars(
        select(Transferencia).where(Transferencia.empresa_origem_id.in_(ids_empresas))
    ).all()
    assert all(t.id_erp.startswith(PREFIXO_SIMULADO) for t in transferencias)
    assert all(t.raw_data["simulado"] is True for t in transferencias)
    for t in transferencias:
        assert all(i.id_produto_erp.startswith(PREFIXO_SIMULADO) for i in t.itens)
        assert all(i.raw_data["simulado"] is True for i in t.itens)
        assert all(i.descricao_produto.startswith("Produto Demonstração") for i in t.itens)

    eventos = limpo.scalars(select(Evento).where(Evento.empresa_id.in_(ids_empresas))).all()
    assert eventos and all(e.origem == ORIGEM_EVENTO for e in eventos)
    assert all(e.payload["simulado"] is True for e in eventos)


@integration
def test_limpar_remove_so_os_simulados(limpo):
    real_a = Empresa(codigo="R01", nome="Empresa de teste A", id_erp="100")
    real_b = Empresa(codigo="R02", nome="Empresa de teste B", id_erp="200")

    real_c = Empresa(codigo="R03", nome="Empresa dev C", id_erp="300", ambiente="development")
    limpo.add_all([real_a, real_b, real_c])
    limpo.add(Transferencia(id_erp="1", empresa_origem=real_a, empresa_destino=real_b))
    limpo.add(Sincronizacao(tipo="transferencias", empresa=real_a))
    limpo.add(Evento(tipo="x", origem="sync", severidade="INFO", empresa=real_a))
    limpo.flush()
    aplicar_seed(limpo, AGORA)

    removidos = limpar_simulados(limpo)

    assert vars(removidos) == {
        "empresas": 6,
        "transferencias": 36,
        "itens": 109,
        "sincronizacoes": 12,
        "eventos": 21,
        "vendas": 2160,
    }
    assert resumo_simulados(limpo)["empresas"] == 0
    assert limpo.scalar(select(Transferencia).where(Transferencia.id_erp == "1")) is not None
    assert limpo.scalar(select(Sincronizacao).where(Sincronizacao.empresa_id == real_a.id))
    assert limpo.scalar(select(Evento).where(Evento.empresa_id == real_a.id))
    assert {e.codigo for e in limpo.scalars(select(Empresa))} >= {"R01", "R02", "R03"}


@integration
def test_limpar_duas_vezes_nao_falha(limpo):
    aplicar_seed(limpo, AGORA)
    limpar_simulados(limpo)

    assert vars(limpar_simulados(limpo)) == {
        "empresas": 0,
        "transferencias": 0,
        "itens": 0,
        "sincronizacoes": 0,
        "eventos": 0,
        "vendas": 0,
    }


@integration
def test_limpar_aborta_se_dado_real_aponta_para_empresa_simulada(limpo):
    aplicar_seed(limpo, AGORA)
    simulada = limpo.scalar(select(Empresa).where(Empresa.codigo == "01"))
    real = Empresa(codigo="R01", nome="Empresa de teste", id_erp="100")
    limpo.add(Transferencia(id_erp="REAL-1", empresa_origem=real, empresa_destino=simulada))
    limpo.flush()

    with pytest.raises(IntegrityError):
        with limpo.begin_nested():
            limpar_simulados(limpo)

    assert resumo_simulados(limpo) == ESPERADO
