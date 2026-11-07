from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database.models import Empresa, PrecoProdutoEmpresa, Transferencia, TransferenciaItem
from app.services.controle_transferencias import Filtros, painel_controle
from tests.conftest import app_com_sessao, token_para

pytestmark = pytest.mark.integration

URL = "/api/v1/transferencias/controle"
AGORA = datetime.now(UTC)


def _transferencia(
    db, n, origem, destino, *, status, horas_atras, horas_entrada=None, itens=(), **extra
):
    criada = AGORA - timedelta(hours=horas_atras)
    t = Transferencia(
        id_erp=str(n),
        numero_nota=str(1000 + n),
        empresa_origem_id=origem.id,
        empresa_destino_id=destino.id,
        empresa_entrada_id=extra.pop("entrada", destino).id if status == "PROCESSADA" else None,
        status=status,
        data_criacao=criada,
        data_processamento=criada + timedelta(hours=horas_entrada) if horas_entrada else None,
        valor_total=extra.pop("valor", Decimal("100.00")),
        usuario_emissao=extra.pop("usuario", "MARIA"),
        coi="8040",
        raw_data=extra.pop("raw", {}),
        itens=[
            TransferenciaItem(
                id_produto_erp=p,
                codigo_produto=p,
                quantidade_solicitada=Decimal(env),
                quantidade_processada=None if rec is None else Decimal(rec),
                valor_total=None if val is None else Decimal(val),
                cfop_saida=cfop,
                cfop_entrada="1152" if status == "PROCESSADA" else None,
            )
            for p, env, rec, val, cfop in itens
        ],
    )
    db.add(t)
    return t


@pytest.fixture
def controle_db(db_vazio):
    db = db_vazio
    e = {c: Empresa(id_erp=c, codigo=c, nome=f"Loja {c}") for c in ("1", "2", "3")}
    db.add_all(e.values())
    db.flush()
    db.add(
        PrecoProdutoEmpresa(
            empresa_id=e["1"].id,
            id_produto="30",
            id_subproduto="30",
            custo_gerencial=Decimal("7.00"),
            sincronizado_em=AGORA,
        )
    )

    _transferencia(
        db,
        1,
        e["1"],
        e["2"],
        status="PROCESSADA",
        horas_atras=10,
        horas_entrada=5,
        itens=[("10", "2", "2", "20.00", "5152")],
    )

    _transferencia(
        db,
        2,
        e["1"],
        e["2"],
        status="PROCESSADA",
        horas_atras=40,
        horas_entrada=30,
        usuario="JOAO",
        itens=[("10", "3", "2", "30.00", "5102")],
    )

    _transferencia(
        db,
        3,
        e["1"],
        e["3"],
        status="PROCESSADA",
        horas_atras=20,
        horas_entrada=2,
        itens=[("30", "1", None, None, "5152")],
        raw={"itens_sem_saida": [{"id_produto": "99", "quantidade": "1"}]},
    )

    _transferencia(
        db, 4, e["2"], e["3"], status="PENDENTE", horas_atras=30, valor=Decimal("250.00")
    )

    _transferencia(
        db,
        7,
        e["1"],
        e["2"],
        status="PROCESSADA",
        horas_atras=8,
        horas_entrada=1,
        itens=[("10", "1000", "1000", "10.00", "5152"), ("10", "3000", "3000", "30.00", "5152")],
    )

    _transferencia(db, 5, e["2"], e["1"], status="CANCELADA", horas_atras=5)

    _transferencia(
        db, 6, e["3"], e["1"], status="PROCESSADA", horas_atras=6, horas_entrada=1, entrada=e["2"]
    )
    db.flush()
    return db, e


@pytest.fixture
def api(controle_db, criar_usuario_teste):
    db, _ = controle_db
    operador = criar_usuario_teste("op.controle", "OPERADOR", modulos=["TRANSFERENCIAS"])
    app = app_com_sessao(db)
    yield TestClient(app, headers=token_para(app, operador))
    app.dependency_overrides.clear()


def test_painel_sem_periodo_nao_monta_um_parametro_por_transferencia(controle_db):
    db, e = controle_db
    for n in range(100, 250):
        _transferencia(
            db,
            n,
            e["1"],
            e["2"],
            status="PROCESSADA",
            horas_atras=60,
            horas_entrada=50,
            itens=[("10", "2", "1", "20.00", "5152")],
        )
    db.flush()
    parametros: list[int] = []

    def contar(_conn, _cursor, _sql, params, _contexto, _executemany):
        parametros.append(len(params) if params else 0)

    conexao = db.connection()
    event.listen(conexao, "before_cursor_execute", contar)
    try:
        painel = painel_controle(db, Filtros(), tz=ZoneInfo("America/Porto_Velho"), agora=AGORA)
    finally:
        event.remove(conexao, "before_cursor_execute", contar)

    assert len(painel.divergencias) == 50
    assert max(parametros) < 50


def test_sem_modulo_403(db_vazio, criar_usuario_teste):
    operador = criar_usuario_teste("op.sem.transf", "OPERADOR", modulos=["DASHBOARD"])
    app = app_com_sessao(db_vazio)
    assert TestClient(app, headers=token_para(app, operador)).get(URL).status_code == 403


def test_painel_resume_transito_prazo_divergencia_e_fiscal(api):
    corpo = api.get(URL).json()
    resumo = corpo["resumo"]
    assert resumo["em_transito_quantidade"] == 1
    assert Decimal(resumo["em_transito_valor"]) == Decimal("250.00")
    assert resumo["fora_do_prazo"] == 2
    assert resumo["divergentes"] == 2

    assert Decimal(resumo["valor_divergencia"]) == Decimal("17.00")
    assert resumo["problemas_fiscais"] == 3
    assert resumo["sem_tratativa"] == 5

    tipos = sorted(p["tipo"] for p in corpo["fiscal"])
    assert tipos == ["CANCELADA", "CFOP_SAIDA", "ENTRADA_OUTRA_EMPRESA"]

    sem_item = next(d for d in corpo["divergencias"] if d["transferencia"]["numero_nota"] == "1003")
    assert {(i["id_produto"], i["sem_saida"]) for i in sem_item["itens"]} == {
        ("30", False),
        ("99", True),
    }

    rota = next(
        r for r in corpo["rotas"] if (r["origem"]["codigo"], r["destino"]["codigo"]) == ("1", "2")
    )
    assert (rota["enviadas"], rota["recebidas"], rota["fora_do_prazo"], rota["divergentes"]) == (
        3,
        3,
        1,
        1,
    )
    assert rota["prazo_horas"] == 24 and rota["prazo_padrao"] is True
    assert rota["tempo_medio_horas"] == 12.0

    joao = next(e for e in corpo["emissores"] if e["usuario"] == "JOAO")
    assert (joao["fora_do_prazo"], joao["divergentes"], joao["problemas_fiscais"]) == (1, 1, 1)


def test_filtro_de_empresa_pega_origem_ou_destino(api):
    corpo = api.get(URL, params={"empresa": "3"}).json()
    numeros = {d["transferencia"]["numero_nota"] for d in corpo["divergencias"]}
    assert numeros == {"1003"}
    assert corpo["resumo"]["em_transito_quantidade"] == 1


def _notas_da_lista(api, **params):
    corpo = api.get("/api/v1/transferencias", params={"tamanho_pagina": 100, **params}).json()
    return {t["numero_nota"] for t in corpo["itens"]}


@pytest.mark.parametrize(
    ("ocorrencia", "notas", "cartao"),
    [
        ("FORA_DO_PRAZO", {"1002", "1004"}, "fora_do_prazo"),
        ("DIVERGENTE", {"1002", "1003"}, "divergentes"),
        ("FISCAL", {"1002", "1005", "1006"}, "problemas_fiscais"),
        ("SEM_TRATATIVA", {"1002", "1003", "1004", "1005", "1006"}, "sem_tratativa"),
    ],
)
def test_lista_filtrada_pela_ocorrencia_bate_com_o_cartao(api, ocorrencia, notas, cartao):

    assert _notas_da_lista(api, ocorrencia=ocorrencia) == notas
    assert api.get(URL).json()["resumo"][cartao] == len(notas)


def test_lista_por_ocorrencia_respeita_empresa_e_emissor(api):
    assert _notas_da_lista(api, ocorrencia="DIVERGENTE", empresa="3") == {"1003"}
    assert _notas_da_lista(api, emitida_por=" joao ") == {"1002"}
    assert _notas_da_lista(api, emitida_por="JOAO", ocorrencia="FISCAL") == {"1002"}
    assert api.get("/api/v1/transferencias", params={"ocorrencia": "OUTRA"}).status_code == 422


def test_prazo_da_rota_muda_o_fora_do_prazo_e_so_admin_grava(api, controle_db, criar_usuario_teste):
    db, _ = controle_db
    assert (
        api.put(
            "/api/v1/transferencias/prazos", json=[{"origem": "1", "destino": "2", "horas": 48}]
        ).status_code
        == 403
    )

    admin = criar_usuario_teste("adm.controle", "ADMIN", modulos=["TRANSFERENCIAS"])
    app = app_com_sessao(db)
    cliente_admin = TestClient(app, headers=token_para(app, admin))
    resposta = cliente_admin.put(
        "/api/v1/transferencias/prazos", json=[{"origem": "1", "destino": "2", "horas": 48}]
    )
    assert resposta.status_code == 200
    assert resposta.json()["prazos"] == [{"origem": "1", "destino": "2", "horas": 48}]

    rota = next(
        r
        for r in api.get(URL).json()["rotas"]
        if r["origem"]["codigo"] == "1" and r["destino"]["codigo"] == "2"
    )
    assert (rota["prazo_horas"], rota["prazo_padrao"], rota["fora_do_prazo"]) == (48, False, 0)

    volta = cliente_admin.put(
        "/api/v1/transferencias/prazos", json=[{"origem": "1", "destino": "2", "horas": None}]
    )
    assert volta.json()["prazos"] == []
    invalido = cliente_admin.put(
        "/api/v1/transferencias/prazos", json=[{"origem": "1", "destino": "9", "horas": 5}]
    )
    assert invalido.status_code == 422


def test_limites_so_admin_grava_e_mudam_o_prazo_padrao_e_o_dashboard(
    api, controle_db, criar_usuario_teste
):
    db, _ = controle_db
    padrao = api.get("/api/v1/transferencias/limites").json()
    assert (padrao["horas_atencao"], padrao["horas_critico"], padrao["definido_por"]) == (
        24,
        48,
        None,
    )
    novos = {"horas_atencao": 36, "horas_critico": 72}
    assert api.put("/api/v1/transferencias/limites", json=novos).status_code == 403

    admin = criar_usuario_teste("adm.limites", "ADMIN", modulos=["TRANSFERENCIAS", "DASHBOARD"])
    app = app_com_sessao(db)
    cliente_admin = TestClient(app, headers=token_para(app, admin))
    for invalido in (
        {"horas_atencao": 48, "horas_critico": 48},
        {"horas_atencao": 50, "horas_critico": 40},
        {"horas_atencao": 0, "horas_critico": 40},
        {"horas_atencao": 24, "horas_critico": 721},
    ):
        assert cliente_admin.put("/api/v1/transferencias/limites", json=invalido).status_code == (
            422
        ), invalido

    gravado = cliente_admin.put("/api/v1/transferencias/limites", json=novos).json()
    assert (gravado["horas_atencao"], gravado["horas_critico"]) == (36, 72)
    assert gravado["definido_por"] == admin.nome_exibicao
    assert api.get("/api/v1/transferencias/limites").json()["horas_atencao"] == 36

    corpo = api.get(URL).json()
    assert corpo["prazo_padrao_horas"] == 36
    assert corpo["resumo"]["fora_do_prazo"] == 0
    assert api.get("/api/v1/transferencias/prazos").json()["prazo_padrao_horas"] == 36

    dashboard = cliente_admin.get("/api/v1/dashboard/resumo").json()
    assert dashboard["limites_pendencia"] == {"horas_atencao": 36, "horas_critico": 72}
    assert dashboard["situacao_atual"]["pendentes_atrasadas"] == 0


def test_tratativa_registra_quem_e_aparece_no_painel(api, controle_db):
    db, _ = controle_db
    t2 = db.query(Transferencia).filter_by(numero_nota="1002").one()
    url = f"/api/v1/transferencias/{t2.id}/tratativas"

    criada = api.post(
        url, json={"situacao": "RESOLVIDA", "observacao": "Falta conferida com a loja 2."}
    )
    assert criada.status_code == 201
    assert criada.json()["usuario_nome"] == "Op.Controle"
    assert [t["situacao"] for t in api.get(url).json()] == ["RESOLVIDA"]

    corpo = api.get(URL).json()
    assert corpo["resumo"]["sem_tratativa"] == 4
    div = next(d for d in corpo["divergencias"] if d["transferencia"]["id"] == t2.id)
    assert div["transferencia"]["tratativa"]["situacao"] == "RESOLVIDA"

    assert (
        api.post(
            "/api/v1/transferencias/999999/tratativas",
            json={"situacao": "EM_ANALISE", "observacao": "xyz"},
        ).status_code
        == 404
    )
    assert api.post(url, json={"situacao": "OUTRA", "observacao": "xyz"}).status_code == 422
