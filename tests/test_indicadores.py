from collections import Counter, defaultdict
from datetime import date, timedelta

import pytest

from app.database.simulacao import EMPRESAS
from app.database.simulacao import TRANSFERENCIAS as TODAS_TRANSFERENCIAS
from app.dominio.intervalo import Intervalo
from app.services.indicadores import chaves_dos_baldes, granularidade_do_intervalo

TRANSFERENCIAS = [t for t in TODAS_TRANSFERENCIAS if t.entre_empresas]

integration = pytest.mark.integration
URL = "/api/v1/dashboard/indicadores-empresas"


@pytest.mark.parametrize(
    ("inicio", "fim", "esperado"),
    [
        (date(2026, 10, 2), date(2026, 10, 2), "hora"),
        (date(2026, 10, 1), date(2026, 10, 2), "dia"),
        (date(2026, 8, 1), date(2026, 10, 1), "dia"),
        (date(2026, 8, 1), date(2026, 10, 2), "mes"),
    ],
)
def test_granularidade_pelo_tamanho_do_periodo(inicio, fim, esperado):
    assert granularidade_do_intervalo(Intervalo(inicio, fim)) == esperado


def test_baldes_cobrem_o_periodo_inteiro():
    dia = Intervalo(date(2026, 10, 2), date(2026, 10, 2))
    assert chaves_dos_baldes(dia, "hora")[0] == "2026-10-02T00"
    assert len(chaves_dos_baldes(dia, "hora")) == 24

    semana = Intervalo(date(2026, 9, 28), date(2026, 10, 4))
    assert chaves_dos_baldes(semana, "dia") == [
        "2026-09-28",
        "2026-09-29",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
    ]

    virada = Intervalo(date(2025, 11, 15), date(2026, 2, 3))
    assert chaves_dos_baldes(virada, "mes") == ["2025-11", "2025-12", "2026-01", "2026-02"]


@integration
def test_totais_por_empresa_batem_com_o_seed(api):
    resposta = api.get(URL)

    assert resposta.status_code == 200
    corpo = resposta.json()

    assert corpo["granularidade"] == "dia"
    assert [e["empresa"]["codigo"] for e in corpo["empresas"]] == list(EMPRESAS)

    monitoradas = [t for t in TRANSFERENCIAS if t.status != "CANCELADA"]
    enviadas = Counter(t.origem for t in monitoradas)
    itens = Counter()
    aguardando = Counter()
    para = Counter()
    com_entrada = Counter()
    a_receber = Counter()
    coi_errado = Counter()
    horas: dict[str, list[float]] = defaultdict(list)
    for t in monitoradas:
        itens[t.origem] += len(t.itens)
        coi_errado[t.origem] += bool(t.problemas_coi)
        if t.status == "PENDENTE":
            aguardando[t.origem] += 1
        if t.destino == t.origem:
            continue
        para[t.destino] += 1
        coi_errado[t.destino] += bool(t.problemas_coi)
        if t.status == "PENDENTE":
            a_receber[t.destino] += 1
        if t.status == "PROCESSADA":
            com_entrada[t.destino] += 1
            if t.processada_ha is not None:
                horas[t.destino].append((t.criada_ha - t.processada_ha) / timedelta(hours=1))

    for empresa in corpo["empresas"]:
        codigo = empresa["empresa"]["codigo"]
        totais = empresa["totais"]
        assert totais["enviadas"] == enviadas[codigo]
        assert totais["itens_enviados"] == itens[codigo]
        assert totais["aguardando_destino"] == aguardando[codigo]
        assert totais["a_receber"] == a_receber[codigo]
        assert totais["recebidas"] == len(horas[codigo])
        assert totais["coi_errado"] == coi_errado[codigo]
        assert totais["taxa_entrada"] == (
            round(com_entrada[codigo] * 100 / para[codigo], 1) if para[codigo] else None
        )
        assert totais["tempo_medio_entrada_horas"] == (
            round(sum(horas[codigo]) / len(horas[codigo]), 1) if horas[codigo] else None
        )

        serie = empresa["serie"]
        assert (
            len(serie)
            == (
                date.fromisoformat(corpo["data_final"]) - date.fromisoformat(corpo["data_inicial"])
            ).days
            + 1
        )
        assert sum(p["enviadas"] for p in serie) == totais["enviadas"]
        assert sum(p["a_receber"] for p in serie) == totais["a_receber"]
        assert sum(p["recebidas"] for p in serie) == totais["recebidas"]


@integration
def test_periodo_de_um_dia_agrupa_por_hora(api):
    hoje = api.get(URL).json()["data_final"]

    corpo = api.get(URL, params={"data_inicial": hoje, "data_final": hoje}).json()

    assert corpo["granularidade"] == "hora"
    assert all(len(e["serie"]) == 24 for e in corpo["empresas"])


@integration
def test_filtro_por_empresa_devolve_so_ela(api):
    corpo = api.get(URL, params={"empresa": "03"}).json()

    assert [e["empresa"]["codigo"] for e in corpo["empresas"]] == ["03"]


@integration
def test_empresa_inexistente_da_404(api):
    assert api.get(URL, params={"empresa": "99"}).status_code == 404


@integration
def test_numero_de_queries_nao_depende_das_empresas(api, contar_queries):
    with contar_queries() as comandos:
        api.get(URL)

    assert len(comandos) == 5


@pytest.mark.parametrize(
    "params",
    [
        {"data_inicial": "2026-09-01"},
        {"data_inicial": "2026-09-10", "data_final": "2026-09-01"},
    ],
)
def test_intervalo_invalido_da_422(client_autorizado, params):
    assert client_autorizado.get(URL, params=params).status_code == 422
