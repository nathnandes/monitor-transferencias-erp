from datetime import UTC, datetime

import pytest

from app.services.pipeline import etapas, situacao_coi

CRIADA = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
PROCESSADA = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
ERRADO = ["COI de saida 8051 nao e da empresa 2 (esperado: 8044)"]


def _estados(status, problemas=(), coi_entrada=None, processada=None):
    return {
        e.chave: e.estado for e in etapas(status, list(problemas), coi_entrada, CRIADA, processada)
    }


@pytest.mark.parametrize(
    ("status", "problemas", "coi_entrada", "esperada"),
    [
        ("PROCESSADA", [], "7161", "CORRETO"),
        ("PENDENTE", [], None, "AGUARDANDO"),
        ("PENDENTE", [], "  ", "AGUARDANDO"),
        (None, [], None, "AGUARDANDO"),
        ("PENDENTE", ERRADO, None, "ERRADO"),
        ("processada", ERRADO, "7161", "ERRADO"),
        ("CANCELADA", ERRADO, None, "AGUARDANDO"),
        (" cancelada ", ERRADO, "7161", "CORRETO"),
    ],
)
def test_situacao_coi(status, problemas, coi_entrada, esperada):
    assert situacao_coi(status, problemas, coi_entrada) == esperada


def test_entrada_com_cois_certos_percorre_o_pipeline_inteiro():
    lista = etapas("PROCESSADA", [], "7161", CRIADA, PROCESSADA)

    assert [e.chave for e in lista] == ["criada", "processamento", "coi", "concluida"]
    assert [e.rotulo for e in lista] == [
        "Saída emitida",
        "Entrada no destino",
        "COIs conferidos",
        "Concluída",
    ]
    assert [e.estado for e in lista] == ["concluida"] * 4
    assert lista[0].momento == CRIADA
    assert lista[1].momento == lista[3].momento == PROCESSADA


def test_coi_errado_falha_na_etapa_do_coi_com_o_problema_no_detalhe():
    lista = etapas("PROCESSADA", ERRADO, "7161", CRIADA, PROCESSADA)
    assert [e.estado for e in lista] == ["concluida", "concluida", "falha", "pendente"]
    assert lista[2].detalhe == ERRADO[0]


def test_coi_de_saida_errado_ja_falha_antes_da_entrada():
    assert _estados("PENDENTE", ERRADO) == {
        "criada": "concluida",
        "processamento": "atual",
        "coi": "falha",
        "concluida": "pendente",
    }


def test_pendente_aguarda_a_entrada():
    lista = etapas("PENDENTE", [], None, CRIADA, None)
    assert [e.estado for e in lista] == ["concluida", "atual", "pendente", "pendente"]
    assert lista[1].detalhe == "Aguardando a entrada"


def test_cancelada_falha_na_saida_e_para_ai():
    lista = etapas("CANCELADA", ERRADO, None, CRIADA, None)
    assert [e.estado for e in lista] == ["falha", "pendente", "pendente", "pendente"]
    assert lista[0].detalhe == "Nota de saída cancelada"


def test_erro_falha_no_processamento():
    assert _estados("ERRO") == {
        "criada": "concluida",
        "processamento": "falha",
        "coi": "pendente",
        "concluida": "pendente",
    }


def test_status_desconhecido_aparece_no_detalhe():
    processamento = etapas("EM TRANSITO", [], None, CRIADA, None)[1]
    assert processamento.estado == "atual"
    assert processamento.detalhe == "Status: EM TRANSITO"
