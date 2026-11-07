from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select, update

from app.database.models import Devolucao, Empresa, Evento, Sincronizacao, Transferencia, Venda
from app.database.simulacao import EMPRESAS, EVENTOS
from app.database.simulacao import TRANSFERENCIAS as TODAS_TRANSFERENCIAS
from app.dominio.transferencias import Limites
from app.services.dashboard import ContagemEmpresa, classificar_empresa

TRANSFERENCIAS = [t for t in TODAS_TRANSFERENCIAS if t.entre_empresas]

integration = pytest.mark.integration
URL = "/api/v1/dashboard/resumo"


@pytest.mark.parametrize(
    ("sincronizacao", "contagem", "esperado"),
    [
        ("sucesso", ContagemEmpresa(), "ok"),
        ("em_andamento", ContagemEmpresa(), "ok"),
        ("sucesso", ContagemEmpresa(pendentes=3), "ok"),
        ("parcial", ContagemEmpresa(), "atencao"),
        (None, ContagemEmpresa(), "atencao"),
        ("sucesso", ContagemEmpresa(pendentes=1, pendentes_atrasadas=1), "atencao"),
        ("erro", ContagemEmpresa(), "critico"),
        ("sucesso", ContagemEmpresa(com_erro=1), "critico"),
        ("sucesso", ContagemEmpresa(pendentes=1, pendentes_criticas=1), "critico"),
        ("parcial", ContagemEmpresa(com_erro=1), "critico"),
        (None, ContagemEmpresa(pendentes=1, pendentes_criticas=1), "critico"),
    ],
)
def test_classificacao_de_empresa(sincronizacao, contagem, esperado):
    status, motivos = classificar_empresa(sincronizacao, contagem)

    assert status == esperado
    assert bool(motivos) == (esperado != "ok")


def test_motivos_listam_todas_as_condicoes_criticas_antes_das_de_atencao():
    contagem = ContagemEmpresa(pendentes=3, pendentes_atrasadas=1, pendentes_criticas=2, com_erro=4)

    status, motivos = classificar_empresa("parcial", contagem)

    assert status == "critico"
    assert motivos == [
        "4 transferência(s) com status ERRO.",
        "2 transferência(s) pendente(s) há mais de 48h.",
        "Última sincronização foi parcial.",
        "1 transferência(s) pendente(s) há mais de 24h.",
    ]


def test_motivos_mostram_os_limites_mudados_na_tela():
    contagem = ContagemEmpresa(pendentes=2, pendentes_atrasadas=1, pendentes_criticas=1)

    _, motivos = classificar_empresa("sucesso", contagem, Limites(12, 36))

    assert motivos == [
        "1 transferência(s) pendente(s) há mais de 36h.",
        "1 transferência(s) pendente(s) há mais de 12h.",
    ]


@integration
def test_resumo_do_dashboard(api):
    resposta = api.get(URL)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "gerado_em",
        "filtro",
        "periodo",
        "comparacao",
        "situacao_atual",
        "transferencias",
        "empresas_ativas",
        "ultima_sincronizacao",
        "eventos_por_severidade",
        "status_por_empresa",
        "limites_pendencia",
    }
    assert corpo["limites_pendencia"] == {"horas_atencao": 24, "horas_critico": 48}

    status = Counter(t.status for t in TRANSFERENCIAS)
    assert corpo["transferencias"] == {
        "total": len(TRANSFERENCIAS),
        "processadas": status["PROCESSADA"],
        "pendentes": status["PENDENTE"],
        "com_erro": status["ERRO"],
    }
    assert corpo["empresas_ativas"] == 6

    severidades = Counter(e.severidade for e in EVENTOS)
    assert corpo["eventos_por_severidade"] == {
        s: severidades[s] for s in ("INFO", "WARNING", "ERROR", "CRITICAL")
    }
    assert sum(corpo["eventos_por_severidade"].values()) == len(EVENTOS)

    gerado_em = datetime.fromisoformat(corpo["gerado_em"])
    assert corpo["gerado_em"].endswith("Z")
    assert abs(datetime.now(UTC) - gerado_em) < timedelta(minutes=1)


@integration
def test_ultima_sincronizacao_e_a_mais_recente_de_todas(api):
    ultima = api.get(URL).json()["ultima_sincronizacao"]

    assert ultima["empresa"]["codigo"] == "06"
    assert ultima["status"] == "erro"
    assert ultima["mensagem_erro"]
    assert ultima["inicio"].endswith("Z")


@integration
def test_status_por_empresa_no_seed(api):
    linhas = api.get(URL).json()["status_por_empresa"]

    assert [s["empresa"]["codigo"] for s in linhas] == EMPRESAS
    por_codigo = {s["empresa"]["codigo"]: s for s in linhas}
    assert {c: s["status"] for c, s in por_codigo.items()} == {
        "01": "ok",
        "02": "critico",
        "03": "critico",
        "04": "ok",
        "05": "ok",
        "06": "critico",
    }

    assert por_codigo["01"]["motivos"] == []
    assert por_codigo["01"]["pendentes"] == 1
    assert por_codigo["03"] | {"empresa": None, "ultima_sincronizacao": None} == {
        "empresa": None,
        "status": "critico",
        "motivos": [
            "1 transferência(s) com status ERRO.",
            "2 transferência(s) pendente(s) há mais de 48h.",
            "Última sincronização foi parcial.",
            "1 transferência(s) pendente(s) há mais de 24h.",
        ],
        "ultima_sincronizacao": None,
        "pendentes": 3,
        "pendentes_atrasadas": 1,
        "pendentes_criticas": 2,
        "com_erro": 1,
    }
    assert por_codigo["06"]["motivos"][0] == "Última sincronização terminou com erro."

    for codigo, linha in por_codigo.items():
        da_origem = [t for t in TRANSFERENCIAS if t.origem == codigo]
        assert linha["pendentes"] == sum(t.status == "PENDENTE" for t in da_origem)
        assert linha["com_erro"] == sum(t.status == "ERRO" for t in da_origem)
        assert set(linha["ultima_sincronizacao"]) == {
            "tipo",
            "status",
            "inicio",
            "fim",
            "mensagem_erro",
        }


def _status_de(api, codigo: str) -> dict:
    linhas = api.get(URL).json()["status_por_empresa"]
    return next(s for s in linhas if s["empresa"]["codigo"] == codigo)


def _id_empresa(api_db, codigo: str) -> int:
    return api_db.scalar(select(Empresa.id).where(Empresa.codigo == codigo))


@integration
def test_sincronizacao_parcial_deixa_empresa_em_atencao(api, api_db):
    empresa_id = _id_empresa(api_db, "01")
    ultima = api_db.scalar(
        select(Sincronizacao.id)
        .where(Sincronizacao.empresa_id == empresa_id)
        .order_by(Sincronizacao.inicio.desc())
        .limit(1)
    )
    api_db.execute(update(Sincronizacao).where(Sincronizacao.id == ultima).values(status="parcial"))
    api_db.expunge_all()

    linha = _status_de(api, "01")

    assert (linha["status"], linha["motivos"]) == ("atencao", ["Última sincronização foi parcial."])


@integration
def test_empresa_sem_sincronizacao_fica_em_atencao(api, api_db):
    api_db.execute(
        delete(Sincronizacao).where(Sincronizacao.empresa_id == _id_empresa(api_db, "04"))
    )
    api_db.expunge_all()

    linha = _status_de(api, "04")

    assert linha["status"] == "atencao"
    assert linha["motivos"] == ["Nenhuma sincronização registrada."]
    assert linha["ultima_sincronizacao"] is None


@integration
def test_pendente_entre_24h_e_48h_fica_em_atencao(api, api_db):
    api_db.execute(
        update(Transferencia)
        .where(Transferencia.id_erp == "DEMO-TRF-0001")
        .values(data_criacao=datetime.now(UTC) - timedelta(hours=25))
    )
    api_db.expunge_all()

    linha = _status_de(api, "01")

    assert linha["status"] == "atencao"
    assert (linha["pendentes_atrasadas"], linha["pendentes_criticas"]) == (1, 0)


@integration
def test_empresa_inativa_fica_fora_do_status(api, api_db):
    api_db.execute(update(Empresa).where(Empresa.codigo == "05").values(ativo=False))
    api_db.expunge_all()

    corpo = api.get(URL).json()

    assert corpo["empresas_ativas"] == 5
    assert "05" not in [s["empresa"]["codigo"] for s in corpo["status_por_empresa"]]


@integration
def test_resumo_com_banco_vazio(api_db, api):
    for model in (Evento, Sincronizacao, Transferencia, Venda, Devolucao, Empresa):
        api_db.execute(delete(model))
    api_db.expunge_all()

    corpo = api.get(URL).json()

    assert corpo["transferencias"] == {"total": 0, "processadas": 0, "pendentes": 0, "com_erro": 0}
    assert corpo["empresas_ativas"] == 0
    assert corpo["ultima_sincronizacao"] is None
    assert corpo["eventos_por_severidade"] == {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
    assert corpo["status_por_empresa"] == []


@integration
def test_resumo_usa_numero_fixo_de_queries(api, contar_queries):
    with contar_queries() as comandos:
        assert api.get(URL).status_code == 200

    assert len(comandos) == 7


HOJE = datetime.now(UTC).date()
TUDO = {"data_inicial": str(HOJE - timedelta(days=60)), "data_final": str(HOJE + timedelta(days=1))}
NADA = {"data_inicial": "2001-01-01", "data_final": "2001-01-31"}


@integration
def test_filtro_por_empresa_conta_origem_ou_destino(api):
    corpo = api.get(URL, params={"empresa": "03"}).json()

    da_03 = [t for t in TRANSFERENCIAS if "03" in (t.origem, t.destino)]
    assert corpo["filtro"]["empresa"]["codigo"] == "03"
    assert corpo["transferencias"]["total"] == len(da_03)
    assert corpo["transferencias"]["com_erro"] == sum(t.status == "ERRO" for t in da_03)

    assert [s["empresa"]["codigo"] for s in corpo["status_por_empresa"]] == ["03"]
    assert corpo["empresas_ativas"] == 1
    assert corpo["ultima_sincronizacao"]["empresa"]["codigo"] == "03"

    assert corpo["periodo"] is None
    assert corpo["comparacao"] is None


@integration
def test_periodo_recorta_transferencias_e_eventos_mas_nao_a_situacao_atual(api):
    corpo = api.get(URL, params=NADA).json()

    assert corpo["transferencias"] == {"total": 0, "processadas": 0, "pendentes": 0, "com_erro": 0}
    assert sum(corpo["eventos_por_severidade"].values()) == 0
    assert corpo["periodo"] == {"criadas": 0, "processadas": 0, "eventos": 0}

    pendentes = [t for t in TRANSFERENCIAS if t.status == "PENDENTE"]
    assert corpo["situacao_atual"] == {
        "pendentes": len(pendentes),
        "pendentes_atrasadas": sum(t.criada_ha > timedelta(hours=24) for t in pendentes),
        "com_erro": sum(t.status == "ERRO" for t in TRANSFERENCIAS),
    }
    assert len(corpo["status_por_empresa"]) == 6


@integration
def test_comparacao_devolve_o_fluxo_do_outro_intervalo(api):
    params = {
        **NADA,
        "comparar_inicial": TUDO["data_inicial"],
        "comparar_final": TUDO["data_final"],
    }
    corpo = api.get(URL, params=params).json()

    assert corpo["filtro"]["comparar_inicial"] == TUDO["data_inicial"]
    assert corpo["periodo"] == {"criadas": 0, "processadas": 0, "eventos": 0}
    assert corpo["comparacao"] == {
        "criadas": len(TRANSFERENCIAS),
        "processadas": sum(t.processada_ha is not None for t in TRANSFERENCIAS),
        "eventos": len(EVENTOS),
    }


@integration
def test_periodo_que_cobre_tudo_bate_com_o_resumo_sem_filtro(api):
    sem_filtro = api.get(URL).json()
    com_periodo = api.get(URL, params=TUDO).json()

    assert com_periodo["transferencias"] == sem_filtro["transferencias"]
    assert com_periodo["eventos_por_severidade"] == sem_filtro["eventos_por_severidade"]
    assert com_periodo["periodo"]["criadas"] == len(TRANSFERENCIAS)


@integration
@pytest.mark.parametrize(
    "params",
    [
        {"data_inicial": "2026-09-01"},
        {"data_inicial": "2026-09-10", "data_final": "2026-09-01"},
        {"comparar_inicial": "2026-09-01", "comparar_final": "2026-09-02"},
    ],
)
def test_intervalos_invalidos_dao_422(api, params):
    assert api.get(URL, params=params).status_code == 422


@integration
def test_empresa_inexistente_da_404(api):
    resposta = api.get(URL, params={"empresa": "99"})
    assert resposta.status_code == 404
    assert "99" in resposta.json()["detail"]


@integration
def test_resumo_filtrado_tambem_usa_numero_fixo_de_queries(api, contar_queries):
    params = {
        "empresa": "02",
        **TUDO,
        "comparar_inicial": "2001-01-01",
        "comparar_final": "2001-01-02",
    }
    with contar_queries() as comandos:
        assert api.get(URL, params=params).status_code == 200

    assert len(comandos) == 8


@integration
def test_listagem_de_transferencias_filtra_por_empresa_em_qualquer_ponta(api):
    corpo = api.get(
        "/api/v1/transferencias", params={"empresa": "05", "tamanho_pagina": 100}
    ).json()

    assert corpo["total"] == sum("05" in (t.origem, t.destino) for t in TRANSFERENCIAS)
    for t in corpo["itens"]:
        assert "05" in (t["empresa_origem"]["codigo"], t["empresa_destino"]["codigo"])
