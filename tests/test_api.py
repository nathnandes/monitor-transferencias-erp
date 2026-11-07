from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from psycopg.errors import ReadOnlySqlTransaction
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database.simulacao import DIVERGENTES, EMPRESAS
from app.database.simulacao import TRANSFERENCIAS as TODAS_TRANSFERENCIAS

integration = pytest.mark.integration
TZ = ZoneInfo("America/Sao_Paulo")


TRANSFERENCIAS = [t for t in TODAS_TRANSFERENCIAS if t.entre_empresas]
TOTAL = len(TRANSFERENCIAS)
CAMPOS_PROIBIDOS = {"raw_data", "payload", "hash_payload", "password_hash"}


def _todas(api, **params) -> list[dict]:
    resposta = api.get("/api/v1/transferencias", params={"tamanho_pagina": 100, **params})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["itens"]


def _dia_local(valor: str) -> date:
    return datetime.fromisoformat(valor).astimezone(TZ).date()


def _chaves(valor: Any) -> set[str]:
    if isinstance(valor, dict):
        return set(valor) | {c for v in valor.values() for c in _chaves(v)}
    if isinstance(valor, list):
        return {c for v in valor for c in _chaves(v)}
    return set()


@pytest.mark.parametrize(
    "rota",
    [
        "/api/v1/empresas",
        "/api/v1/transferencias",
        "/api/v1/transferencias/1",
        "/api/v1/dashboard/resumo",
        "/health/live",
        "/health/ready",
    ],
)
@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
def test_metodos_de_escrita_nao_existem(client, rota, metodo):
    assert client.request(metodo, rota).status_code == 405


def test_openapi_documenta_rotas_e_contratos(client):
    openapi = client.get("/openapi.json").json()

    consulta = {
        "/health/live",
        "/health/ready",
        "/api/v1/empresas",
        "/api/v1/transferencias",
        "/api/v1/transferencias/{id}",
        "/api/v1/dashboard/resumo",
        "/api/v1/alertas",
        "/api/v1/alertas/resumo",
        "/api/v1/dashboard/indicadores-empresas",
        "/api/v1/estoque",
        "/api/v1/estoque/resumo",
        "/api/v1/estoque/cobertura",
        "/api/v1/estoque/cobertura/lojas",
        "/api/v1/estoque/movimentos",
        "/api/v1/estoque/{id_produto}/{id_subproduto}",
        "/api/v1/estoque/fornecedores",
        "/api/v1/estoque/livro",
        "/api/v1/estoque/livro/notas",
        "/api/v1/estoque/livro/notas/{empresa}/{id_planilha}",
        "/api/v1/estoque/balancos",
        "/api/v1/estoque/balancos/recontagens",
        "/api/v1/estoque/avulsas/documentos",
        "/api/v1/estoque/avulsas/{empresa}/{id_planilha}/candidatos",
        "/api/v1/estoque/{id_produto}/{id_subproduto}/extrato",
        "/api/v1/vendas/resumo",
        "/api/v1/vendas/formas-pagamento/exportar",
        "/api/v1/vendas/descontos/exportar",
        "/api/v1/financeiro/parcelas",
        "/api/v1/financeiro/resumo",
        "/api/v1/frescor",
        "/api/v1/transferencias/exportar",
        "/api/v1/estoque/exportar",
    }

    auth = {
        "/api/v1/auth/login": {"post"},
        "/api/v1/auth/me": {"get"},
        "/api/v1/auth/change-password": {"post"},
        "/api/v1/auth/renew": {"post"},
        "/api/v1/auth/logout": {"post"},
        "/api/v1/auth/permissions": {"get"},
    }

    admin = {
        "/api/v1/admin/users": {"get", "post"},
        "/api/v1/admin/users/{id}": {"get", "patch"},
        "/api/v1/admin/users/{id}/reset-password": {"post"},
        "/api/v1/admin/users/{id}/activate": {"post"},
        "/api/v1/admin/users/{id}/deactivate": {"post"},
        "/api/v1/admin/users/{id}/permissions": {"get", "put"},
        "/api/v1/admin/perfis": {"get", "post"},
        "/api/v1/admin/perfis/{id}": {"put", "delete"},
        "/api/v1/admin/alertas": {"get"},
        "/api/v1/admin/alertas/regras/{regra}": {"put", "delete"},
        "/api/v1/admin/alertas/destinos": {"post"},
        "/api/v1/admin/alertas/destinos/{id}": {"put", "delete"},
        "/api/v1/admin/alertas/modelos/{chave}": {"put", "delete"},
        "/api/v1/admin/alertas/modelos/{chave}/previa": {"post"},
        "/api/v1/admin/alertas/mensagens": {"get", "post"},
        "/api/v1/admin/alertas/mensagens/modelos": {"get", "post"},
        "/api/v1/admin/alertas/mensagens/modelos/{id}": {"delete"},
        "/api/v1/admin/alertas/mensagens/previa": {"post"},
        "/api/v1/admin/alertas/mensagens/variaveis": {"get"},
        "/api/v1/admin/alertas/mensagens/{id}": {"delete"},
        "/api/v1/admin/atividades": {"get"},
        "/api/v1/admin/estoque-baixo": {"get", "put"},
        "/api/v1/admin/estoque-baixo/situacao": {"get"},
        "/api/v1/vendas/metas": {"get", "put"},
        "/api/v1/vendas/metas/progresso": {"get"},
        "/api/v1/vendas/metas/vendedores": {"get"},
        "/api/v1/vendas/metas/marcos": {"put"},
        "/api/v1/vendas/metas/{id}": {"delete"},
    }

    sync = {
        "/api/v1/sync/companies": {"post"},
        "/api/v1/sync/stock": {"post"},
        "/api/v1/sync/stock/full": {"post"},
        "/api/v1/sync/transfers": {"post"},
        "/api/v1/sync/prices": {"post"},
        "/api/v1/sync/prices/full": {"post"},
        "/api/v1/sync/sales": {"post"},
        "/api/v1/sync/stock-movements": {"post"},
        "/api/v1/sync/status": {"get"},
    }

    controle = {
        "/api/v1/transferencias/controle": {"get"},
        "/api/v1/transferencias/prazos": {"get", "put"},
        "/api/v1/transferencias/limites": {"get", "put"},
        "/api/v1/transferencias/anomalias": {"get"},
        "/api/v1/transferencias/{id}/tratativas": {"get", "post"},
    }

    estoque = {
        "/api/v1/estoque/excecoes": {"get", "post"},
        "/api/v1/estoque/pedido-abastecimento": {"get"},
        "/api/v1/estoque/pedido-abastecimento/exportar": {"get"},
        "/api/v1/estoque/excecoes/{empresa}/{id_produto}/{id_subproduto}": {"delete"},
        "/api/v1/estoque/avulsas/corte": {"get", "put"},
        "/api/v1/estoque/avulsas/justificativas": {"put"},
        "/api/v1/estoque/avulsas/{empresa}/{id_planilha}/justificativa": {"put"},
        "/api/v1/estoque/avulsas/{empresa}/{id_planilha}/vinculo": {"put", "delete"},
    }
    assert set(openapi["paths"]) == (
        consulta | set(auth) | set(admin) | set(sync) | set(controle) | set(estoque)
    )

    assert {m for rota in consulta for m in openapi["paths"][rota]} == {"get"}
    for rota, metodos in {**auth, **admin, **sync, **controle, **estoque}.items():
        assert set(openapi["paths"][rota]) == metodos, rota

    schemas = openapi["components"]["schemas"]
    for nome in ("Empresa", "PaginaTransferencias", "TransferenciaDetalhe", "ResumoDashboard"):
        assert nome in schemas, nome

    detalhe = openapi["paths"]["/api/v1/transferencias/{id}"]["get"]["responses"]
    assert detalhe["404"]["content"]["application/json"]["schema"]["$ref"].endswith("/Erro")

    parametros = {
        p["name"]: p for p in openapi["paths"]["/api/v1/transferencias"]["get"]["parameters"]
    }
    assert set(parametros) == {
        "empresa_origem",
        "empresa_destino",
        "empresa",
        "status",
        "situacao_coi",
        "emitida_por",
        "ocorrencia",
        "data_inicial",
        "data_final",
        "pagina",
        "tamanho_pagina",
    }
    assert parametros["tamanho_pagina"]["schema"]["maximum"] == 100


def test_nenhum_schema_publico_expoe_payload_bruto(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    for nome, schema in schemas.items():
        assert not CAMPOS_PROIBIDOS & set(schema.get("properties", {})), nome


@integration
def test_sessao_de_leitura_recusa_escrita(engine):
    from app.database.session import get_session_leitura

    gerador = get_session_leitura()
    sessao = next(gerador)
    try:
        with pytest.raises(DBAPIError) as erro:
            sessao.execute(
                text(
                    "INSERT INTO logs (nivel, modulo, evento, mensagem)"
                    " VALUES ('INFO', 'teste', 'teste', 'nao deve gravar')"
                )
            )

        assert isinstance(erro.value.orig, ReadOnlySqlTransaction)
    finally:
        gerador.close()


@integration
def test_nenhuma_resposta_traz_raw_data(api):
    ids = [t["id"] for t in _todas(api)]
    respostas = [
        api.get("/api/v1/empresas"),
        api.get("/api/v1/transferencias", params={"tamanho_pagina": 100}),
        api.get("/api/v1/dashboard/resumo"),
        *(api.get(f"/api/v1/transferencias/{i}") for i in ids),
    ]

    for resposta in respostas:
        assert resposta.status_code == 200
        assert not CAMPOS_PROIBIDOS & _chaves(resposta.json()), resposta.url


@integration
def test_lista_empresas_ordenadas_por_codigo(api):
    resposta = api.get("/api/v1/empresas")

    assert resposta.status_code == 200
    empresas = resposta.json()
    assert [e["codigo"] for e in empresas] == EMPRESAS
    primeira = empresas[0]
    assert set(primeira) == {
        "id",
        "id_erp",
        "codigo",
        "nome",
        "bairro",
        "ativo",
        "ambiente",
        "created_at",
        "updated_at",
    }
    assert primeira | {"id": 0, "created_at": "", "updated_at": ""} == {
        "id": 0,
        "id_erp": "DEMO-EMP-01",
        "codigo": "01",
        "nome": "Empresa Demonstração 01",
        "bairro": None,
        "ativo": True,
        "ambiente": "development",
        "created_at": "",
        "updated_at": "",
    }
    assert primeira["created_at"].endswith("Z")
    assert primeira["updated_at"].endswith("Z")


@integration
def test_filtra_empresas_por_ativo(api):
    assert len(api.get("/api/v1/empresas", params={"ativo": True}).json()) == 6
    assert api.get("/api/v1/empresas", params={"ativo": False}).json() == []


@integration
def test_primeira_pagina_padrao(api):
    corpo = api.get("/api/v1/transferencias").json()

    assert set(corpo) == {"total", "pagina", "tamanho_pagina", "total_paginas", "itens"}
    assert (corpo["total"], corpo["pagina"], corpo["tamanho_pagina"]) == (TOTAL, 1, 20)
    assert corpo["total_paginas"] == 2
    assert len(corpo["itens"]) == 20

    item = corpo["itens"][0]
    assert set(item) == {
        "id",
        "id_erp",
        "status",
        "empresa_origem",
        "empresa_destino",
        "data_criacao",
        "data_processamento",
        "quantidade_itens",
        "numero_nota",
        "chave_nfe",
        "coi",
        "coi_entrada",
        "problemas_coi",
        "valor_total",
        "usuario_emissao",
        "situacao_coi",
        "etapas",
    }
    assert set(item["empresa_origem"]) == set(item["empresa_destino"]) == {"id", "codigo", "nome"}


@integration
def test_ultima_pagina_traz_o_resto(api):
    corpo = api.get("/api/v1/transferencias", params={"pagina": 2}).json()

    assert corpo["pagina"] == 2
    assert len(corpo["itens"]) == TOTAL - 20


@integration
def test_ordena_da_mais_recente_para_a_mais_antiga(api):
    datas = [datetime.fromisoformat(t["data_criacao"]) for t in _todas(api)]

    assert datas == sorted(datas, reverse=True)
    assert len(datas) == TOTAL


@integration
def test_datas_saem_em_utc(api):
    transferencia = _todas(api, status="PROCESSADA")[0]

    assert transferencia["data_criacao"].endswith("Z")
    assert transferencia["data_processamento"].endswith("Z")


@integration
def test_paginas_nao_se_sobrepoem_e_cobrem_tudo(api):
    ids = []
    for pagina in (1, 2, 3, 4):
        corpo = api.get(
            "/api/v1/transferencias", params={"pagina": pagina, "tamanho_pagina": 10}
        ).json()
        assert corpo["total_paginas"] == 4
        ids += [t["id"] for t in corpo["itens"]]

    assert len(ids) == len(set(ids)) == TOTAL
    assert ids == [t["id"] for t in _todas(api)]


@integration
def test_pagina_alem_do_fim_vem_vazia(api):
    corpo = api.get("/api/v1/transferencias", params={"pagina": 99}).json()

    assert corpo["itens"] == []
    assert corpo["total"] == TOTAL


@integration
def test_tamanho_maximo_de_pagina_e_100(api):
    corpo = api.get("/api/v1/transferencias", params={"tamanho_pagina": 100}).json()

    assert (corpo["tamanho_pagina"], corpo["total_paginas"], len(corpo["itens"])) == (
        100,
        1,
        TOTAL,
    )


@integration
@pytest.mark.parametrize(
    "params",
    [{"pagina": 0}, {"tamanho_pagina": 0}, {"tamanho_pagina": 101}, {"pagina": "x"}],
)
def test_paginacao_invalida_responde_422(api, params):
    assert api.get("/api/v1/transferencias", params=params).status_code == 422


@integration
def test_filtra_por_empresa_origem(api):
    itens = _todas(api, empresa_origem="01")

    assert len(itens) == sum(t.origem == "01" for t in TRANSFERENCIAS)
    assert {t["empresa_origem"]["codigo"] for t in itens} == {"01"}


@integration
def test_filtra_por_empresa_destino(api):
    itens = _todas(api, empresa_destino="03")

    assert len(itens) == sum(t.destino == "03" for t in TRANSFERENCIAS)
    assert {t["empresa_destino"]["codigo"] for t in itens} == {"03"}


@integration
@pytest.mark.parametrize("status", ["PENDENTE", "pendente", "Erro", "PROCESSADA"])
def test_filtra_por_status_sem_diferenciar_maiusculas(api, status):
    itens = _todas(api, status=status)

    esperado = Counter(t.status for t in TRANSFERENCIAS)[status.upper()]
    assert len(itens) == esperado
    assert {t["status"] for t in itens} == {status.upper()}


def _situacao_coi_esperada(t) -> str:
    if t.problemas_coi:
        return "ERRADO"
    return "CORRETO" if t.coi_entrada else "AGUARDANDO"


@integration
@pytest.mark.parametrize("situacao", ["CORRETO", "ERRADO", "AGUARDANDO"])
def test_filtra_por_situacao_do_coi(api, situacao):
    itens = _todas(api, situacao_coi=situacao)

    esperado = sum(_situacao_coi_esperada(t) == situacao for t in TRANSFERENCIAS)
    assert esperado > 0
    assert len(itens) == esperado
    assert {t["situacao_coi"] for t in itens} == {situacao}


@integration
def test_situacao_coi_invalida_e_422(api):
    resposta = api.get("/api/v1/transferencias", params={"situacao_coi": "TALVEZ"})
    assert resposta.status_code == 422


@integration
def test_pipeline_da_transferencia_com_coi_errado_marca_falha_no_coi(api):
    item = _todas(api, situacao_coi="ERRADO")[0]

    etapas = {e["chave"]: e for e in item["etapas"]}
    assert list(etapas) == ["criada", "processamento", "coi", "concluida"]
    assert etapas["coi"]["estado"] == "falha"
    assert item["problemas_coi"]
    assert item["problemas_coi"][0] in etapas["coi"]["detalhe"]
    assert etapas["concluida"]["estado"] == "pendente"


@integration
def test_pipeline_da_transferencia_com_cois_certos_termina_concluida(api):
    item = _todas(api, situacao_coi="CORRETO")[0]

    assert [e["estado"] for e in item["etapas"]] == ["concluida"] * 4
    assert item["coi"] and item["coi_entrada"] and item["problemas_coi"] == []


@integration
def test_filtra_por_data_inicial(api):
    todas = _todas(api)
    inicio = date.today() - timedelta(days=10)

    itens = _todas(api, data_inicial=inicio.isoformat())

    esperado = [t["id"] for t in todas if _dia_local(t["data_criacao"]) >= inicio]
    assert [t["id"] for t in itens] == esperado
    assert 0 < len(itens) < TOTAL


@integration
def test_filtra_por_data_final(api):
    todas = _todas(api)
    fim = date.today() - timedelta(days=3)

    itens = _todas(api, data_final=fim.isoformat())

    esperado = [t["id"] for t in todas if _dia_local(t["data_criacao"]) <= fim]
    assert [t["id"] for t in itens] == esperado
    assert 0 < len(itens) < TOTAL


@integration
def test_intervalo_de_um_dia_e_inclusivo(api):
    todas = _todas(api)
    dia = _dia_local(todas[len(todas) // 2]["data_criacao"])

    itens = _todas(api, data_inicial=dia.isoformat(), data_final=dia.isoformat())

    esperado = [t for t in todas if _dia_local(t["data_criacao"]) == dia]
    assert [t["id"] for t in itens] == [t["id"] for t in esperado]
    assert itens


@integration
def test_empresa_inexistente_retorna_lista_vazia(api):
    corpo = api.get("/api/v1/transferencias", params={"empresa_origem": "99"}).json()

    assert (corpo["itens"], corpo["total"], corpo["total_paginas"]) == ([], 0, 0)


@integration
def test_combina_origem_e_status(api):
    itens = _todas(api, empresa_origem="02", status="PROCESSADA")

    esperado = [t for t in TRANSFERENCIAS if t.origem == "02" and t.status == "PROCESSADA"]
    assert len(itens) == len(esperado) > 0
    assert {(t["empresa_origem"]["codigo"], t["status"]) for t in itens} == {("02", "PROCESSADA")}


@integration
def test_combina_origem_e_destino(api):
    par = (TRANSFERENCIAS[0].origem, TRANSFERENCIAS[0].destino)

    itens = _todas(api, empresa_origem=par[0], empresa_destino=par[1])

    esperado = [t for t in TRANSFERENCIAS if (t.origem, t.destino) == par]
    assert len(itens) == len(esperado) > 0


@integration
def test_combina_todos_os_filtros(api):

    rota = {"empresa_origem": "03", "empresa_destino": "04"}
    hoje = datetime.now(TZ).date()
    datas = {
        "data_inicial": (hoje - timedelta(days=20)).isoformat(),
        "data_final": hoje.isoformat(),
    }

    assert [t["id_erp"] for t in _todas(api, **rota)] == ["DEMO-TRF-0003", "DEMO-TRF-0033"]
    assert [t["id_erp"] for t in _todas(api, **rota, status="erro")] == ["DEMO-TRF-0033"]
    assert _todas(api, **rota, status="erro", **datas) == []
    assert [t["id_erp"] for t in _todas(api, **rota, status="pendente", **datas)] == [
        "DEMO-TRF-0003"
    ]


@integration
def test_filtros_combinados_paginam_sobre_o_total_filtrado(api):
    corpo = api.get(
        "/api/v1/transferencias",
        params={"status": "PROCESSADA", "tamanho_pagina": 5, "pagina": 2},
    ).json()

    processadas = Counter(t.status for t in TRANSFERENCIAS)["PROCESSADA"]
    assert corpo["total"] == processadas
    assert corpo["total_paginas"] == -(-processadas // 5)
    assert len(corpo["itens"]) == 5


@integration
def test_intervalo_de_datas_invertido_responde_422_claro(api):
    resposta = api.get(
        "/api/v1/transferencias",
        params={"data_inicial": "2026-09-20", "data_final": "2026-09-10"},
    )

    assert resposta.status_code == 422
    assert resposta.json() == {
        "detail": "data_inicial (2026-09-20) é posterior a data_final (2026-09-10)."
    }


def test_intervalo_invertido_e_recusado_antes_de_consultar_o_banco(client_autorizado):
    resposta = client_autorizado.get(
        "/api/v1/transferencias",
        params={"data_inicial": "2026-09-20", "data_final": "2026-09-10"},
    )

    assert resposta.status_code == 422


@integration
def test_data_em_formato_invalido_responde_422(api):
    resposta = api.get("/api/v1/transferencias", params={"data_inicial": "25/09/2026"})

    assert resposta.status_code == 422


def _id_por_id_erp(api, id_erp: str) -> int:
    return next(t["id"] for t in _todas(api) if t["id_erp"] == id_erp)


@integration
def test_detalhe_traz_origem_destino_e_itens(api):
    numero = min(DIVERGENTES)
    spec = TODAS_TRANSFERENCIAS[numero - 1]
    id_erp = f"DEMO-TRF-{numero:04d}"

    resposta = api.get(f"/api/v1/transferencias/{_id_por_id_erp(api, id_erp)}")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "id",
        "id_erp",
        "status",
        "empresa_origem",
        "empresa_destino",
        "data_criacao",
        "data_processamento",
        "quantidade_itens",
        "numero_nota",
        "chave_nfe",
        "coi",
        "coi_entrada",
        "problemas_coi",
        "situacao_coi",
        "etapas",
        "created_at",
        "updated_at",
        "valor_total",
        "usuario_emissao",
        "itens",
    }
    assert corpo["id_erp"] == id_erp
    assert corpo["status"] == "PROCESSADA"
    assert corpo["empresa_origem"]["codigo"] == spec.origem
    assert corpo["empresa_destino"]["codigo"] == spec.destino
    assert len(corpo["itens"]) == corpo["quantidade_itens"] == len(spec.itens)
    assert [i["id"] for i in corpo["itens"]] == sorted(i["id"] for i in corpo["itens"])

    primeiro = corpo["itens"][0]
    assert set(primeiro) == {
        "id",
        "id_produto_erp",
        "codigo_produto",
        "descricao_produto",
        "quantidade_solicitada",
        "quantidade_processada",
        "divergente",
        "valor_total",
        "cfop_saida",
        "cfop_entrada",
    }
    assert primeiro["divergente"] is True

    assert isinstance(primeiro["quantidade_solicitada"], str)
    solicitadas = sorted(float(i["quantidade_solicitada"]) for i in corpo["itens"])
    assert solicitadas == sorted(float(i.solicitada) for i in spec.itens)
    assert float(primeiro["quantidade_processada"]) == float(primeiro["quantidade_solicitada"]) - 1


@integration
def test_detalhe_de_pendente_nao_tem_processamento(api):
    corpo = api.get(f"/api/v1/transferencias/{_id_por_id_erp(api, 'DEMO-TRF-0001')}").json()

    assert corpo["status"] == "PENDENTE"
    assert corpo["data_processamento"] is None
    assert all(i["quantidade_processada"] is None for i in corpo["itens"])
    assert all(i["quantidade_solicitada"] is not None for i in corpo["itens"])
    assert not any(i["divergente"] for i in corpo["itens"])


@integration
def test_transferencia_inexistente_responde_404_claro(api):
    resposta = api.get("/api/v1/transferencias/999999999")

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "Transferência 999999999 não encontrada."}


def test_id_nao_numerico_responde_422(client_autorizado):

    assert client_autorizado.get("/api/v1/transferencias/abc").status_code == 422


@integration
@pytest.mark.parametrize("tamanho", [1, 10, 100])
def test_listagem_usa_duas_queries_qualquer_que_seja_a_pagina(api, contar_queries, tamanho):
    with contar_queries() as comandos:
        resposta = api.get("/api/v1/transferencias", params={"tamanho_pagina": tamanho})

    assert resposta.status_code == 200
    assert len(comandos) == 2


@integration
def test_detalhe_usa_duas_queries_qualquer_que_seja_o_numero_de_itens(api, contar_queries):
    maior = max(TRANSFERENCIAS, key=lambda t: len(t.itens))
    id_ = _id_por_id_erp(api, f"DEMO-TRF-{maior.numero:04d}")

    with contar_queries() as comandos:
        corpo = api.get(f"/api/v1/transferencias/{id_}").json()

    assert len(corpo["itens"]) == len(maior.itens) > 1
    assert len(comandos) == 2


def test_exportar_transferencias_traz_o_mesmo_que_a_lista_filtrada(api):
    filtros = {"situacao_coi": "ERRADO"}
    lista = api.get("/api/v1/transferencias", params={"tamanho_pagina": 100, **filtros}).json()

    resposta = api.get("/api/v1/transferencias/exportar", params=filtros)

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert 'filename="transferencias_' in resposta.headers["content-disposition"]
    assert resposta.headers["x-total-registros"] == str(lista["total"])
    linhas = resposta.content.decode("utf-8").lstrip("﻿").splitlines()
    assert linhas[0].split(";")[:3] == ["Nota", "Origem", "Origem (nome)"]
    corpo = [linha.split(";") for linha in linhas[1:]]
    assert [c[0] for c in corpo] == [t["numero_nota"] or "" for t in lista["itens"]]
    assert {c[6] for c in corpo} == {"ERRADO"}


def test_exportar_transferencias_valida_as_datas_como_a_lista(api):
    resposta = api.get(
        "/api/v1/transferencias/exportar",
        params={"data_inicial": "2026-10-10", "data_final": "2026-10-01"},
    )
    assert resposta.status_code == 422
