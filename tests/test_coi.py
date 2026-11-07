import pytest

from app.dominio.coi import (
    COI_ENTRADA,
    COIS_FISCAIS,
    COIS_SAIDA,
    coi_entrada_esperado,
    conferir_transferencia,
    problemas_entrada,
    problemas_saida,
    tipo,
)


def test_catalogo_cobre_as_6_empresas_sem_coi_repetido() -> None:
    assert set(COIS_SAIDA) == set(COI_ENTRADA) == {1, 2, 3, 4, 5, 6}
    saidas = [c for cois in COIS_SAIDA.values() for c in cois]
    assert len(saidas) == len(set(saidas)) == 6
    assert len(set(COI_ENTRADA.values())) == 6
    assert not set(saidas) & set(COI_ENTRADA.values())
    assert not set(saidas) & COIS_FISCAIS


@pytest.mark.parametrize(
    ("coi", "esperado"),
    [(8040, "SAIDA"), (8061, "SAIDA"), (51, "ENTRADA"), (7661, "ENTRADA")],
)
def test_tipo(coi: int, esperado: str) -> None:
    assert tipo(coi) == esperado


@pytest.mark.parametrize("coi", [999, 8060, None])
def test_tipo_de_coi_nao_monitorado(coi: int | None) -> None:
    assert tipo(coi) is None


def test_saida_certa_para_qualquer_destino() -> None:
    for destino in (2, 3, 4, 5, 6):
        assert problemas_saida(1, 8040, destino) == []


def test_saida_com_coi_de_outra_empresa() -> None:
    (problema,) = problemas_saida(2, 8051, 3)
    assert "8051" in problema and "8044" in problema


@pytest.mark.parametrize("destino", [None, 9, 4])
def test_saida_com_destino_invalido(destino: int | None) -> None:
    assert problemas_saida(4, 8039, destino)


def test_entrada_certa_de_qualquer_origem() -> None:
    for origem in (1, 2, 3, 4, 5):
        assert problemas_entrada(6, 7661, origem) == []


def test_matriz_recebe_da_loja_leste_com_a_excecao() -> None:
    assert coi_entrada_esperado(6, 1) == 7661
    assert problemas_entrada(1, 7661, 6) == []
    assert problemas_entrada(1, 51, 6)


def test_matriz_recebe_das_outras_com_51() -> None:
    for origem in (2, 3, 4, 5):
        assert problemas_entrada(1, 51, origem) == []
        assert problemas_entrada(1, 7661, origem)


def test_entrada_com_coi_de_outra_empresa() -> None:
    (problema,) = problemas_entrada(3, 7162, 1)
    assert "7162" in problema and "7161" in problema


@pytest.mark.parametrize("origem", [None, 9, 3])
def test_entrada_com_origem_invalida(origem: int | None) -> None:
    assert problemas_entrada(3, 7161, origem)


def test_conferencia_no_padrao_entre_empresas() -> None:
    c = conferir_transferencia(
        origem="1",
        coi_saida="8040",
        destino="3",
        coi_entrada="7161",
        empresa_entrada="3",
        entrada_registrada=True,
    )
    assert (c.problemas, c.fora_do_padrao, c.entre_empresas) == ([], [], True)


def test_coi_de_outra_empresa_nao_e_erro_e_outro_tipo() -> None:
    c = conferir_transferencia(origem="2", coi_saida="8051", destino="3")
    assert c.problemas == []
    assert c.fora_do_padrao and not c.entre_empresas


def test_coi_errado_e_so_nota_sem_coi() -> None:
    saida = conferir_transferencia(origem="1", coi_saida=None, destino="3")
    entrada = conferir_transferencia(
        origem="1", coi_saida="8040", destino="3", entrada_registrada=True
    )
    assert saida.problemas == ["nota de saida sem COI"]
    assert entrada.problemas == ["nota de entrada sem COI"]
    assert saida.entre_empresas and entrada.entre_empresas


def test_entrada_ainda_nao_feita_nao_e_erro() -> None:
    c = conferir_transferencia(origem="1", coi_saida="8040", destino="3")
    assert (c.problemas, c.entre_empresas) == ([], True)
