import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.anomalias.avaliacao import (
    avaliar_conjunto,
    medir,
    scores_regra_simples,
    separar_por_tempo,
)
from app.anomalias.demo import main
from app.anomalias.features import FEATURES, ExtratorFeatures, divergencia
from app.anomalias.modelo import DetectorAnomalias
from app.anomalias.registros import RegistroTransferencia
from app.anomalias.sintetico import EMPRESAS, TIPOS_ANOMALIA, gerar


@pytest.fixture(scope="module")
def conjunto():
    return gerar(1, quantidade=2_000, taxa_anomalias=0.03)


@pytest.fixture(scope="module")
def detector(conjunto):
    treino, _ = separar_por_tempo(conjunto.registros)
    return DetectorAnomalias(n_estimators=100, semente=1).treinar(treino)


def _registro(**campos) -> RegistroTransferencia:
    emitida = datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
    padrao = {
        "id": "T1",
        "origem": "A",
        "destino": "B",
        "valor": 1_000.0,
        "emitida_em": emitida,
        "recebida_em": emitida + timedelta(hours=10),
        "quantidade_itens": 10,
        "quantidade_enviada": 100.0,
        "quantidade_recebida": 100.0,
    }
    return RegistroTransferencia(**{**padrao, **campos})


def test_gerador_e_deterministico():
    a, b = gerar(5, quantidade=200), gerar(5, quantidade=200)
    assert a.registros == b.registros
    assert a.rotulos == b.rotulos


def test_sementes_diferentes_dao_conjuntos_diferentes():
    assert gerar(5, quantidade=200).registros != gerar(6, quantidade=200).registros


def test_gerador_injeta_todos_os_tipos_na_proporcao_pedida():
    c = gerar(5, quantidade=1_000, taxa_anomalias=0.02)
    assert len(c.rotulos) == 20
    assert set(c.rotulos.values()) == set(TIPOS_ANOMALIA)


def test_gerador_so_usa_nomes_inventados():
    c = gerar(5, quantidade=500)
    assert all(re.fullmatch(r"Empresa 0[1-6]", e) for e in EMPRESAS)
    assert {e for r in c.registros for e in r.rota} <= set(EMPRESAS)
    assert all(r.id.startswith("SIM-") for r in c.registros)


def test_gerador_vem_em_ordem_de_emissao_e_recebimento_nunca_antes_da_emissao():
    c = gerar(5, quantidade=500)
    emissoes = [r.emitida_em for r in c.registros]
    assert emissoes == sorted(emissoes)
    assert all(r.recebida_em >= r.emitida_em for r in c.registros if r.recebida_em)


def test_o_que_seria_recebido_depois_do_fim_fica_pendente():
    c = gerar(5, quantidade=2_000)
    pendentes = [r for r in c.registros if r.pendente]
    assert pendentes
    assert all(r.quantidade_recebida is None for r in pendentes)
    assert all(r.recebida_em <= c.fim for r in c.registros if r.recebida_em)


@pytest.mark.parametrize(
    "parametros", [{"taxa_anomalias": 1.0}, {"taxa_anomalias": -0.1}, {"dias": 3}]
)
def test_gerador_recusa_parametros_invalidos(parametros):
    with pytest.raises(ValueError):
        gerar(1, **parametros)


def test_valor_e_medido_em_relacao_a_propria_rota():
    historico = [
        _registro(id=f"B{i}", origem="A", destino="B", valor=100.0 + i) for i in range(50)
    ] + [_registro(id=f"C{i}", origem="A", destino="C", valor=10_000.0 + i) for i in range(50)]
    extrator = ExtratorFeatures().ajustar(historico)
    x = extrator.transformar(
        [_registro(destino="B", valor=10_000.0), _registro(destino="C", valor=10_000.0)]
    )
    coluna = FEATURES.index("valor_na_rota")
    assert x[0, coluna] > 3
    assert abs(x[1, coluna]) < 1


def test_rota_nunca_vista_usa_o_padrao_geral_e_e_rara():
    historico = [_registro(id=f"B{i}", valor=100.0 + i) for i in range(50)]
    extrator = ExtratorFeatures().ajustar(historico)
    x = extrator.transformar([_registro(origem="X", destino="Y"), _registro()])
    coluna = FEATURES.index("raridade_rota")
    assert x[0, coluna] > x[1, coluna]
    assert np.isfinite(x).all()


def test_rota_com_pouco_historico_nao_tem_padrao_proprio_confiavel():
    historico = [_registro(id=f"B{i}", valor=1_000.0 + i) for i in range(100)] + [
        _registro(id=f"C{i}", destino="C", valor=100_000.0) for i in range(2)
    ]
    extrator = ExtratorFeatures().ajustar(historico)
    assert extrator.padrao_rota(("A", "C")).valor.mediana() < 10_000


def test_pendente_tem_transito_e_divergencia_neutros():
    historico = [_registro(id=f"B{i}", valor=100.0 + i) for i in range(30)]
    extrator = ExtratorFeatures().ajustar(historico)
    x = extrator.transformar([_registro(recebida_em=None, quantidade_recebida=None)])
    assert x[0, FEATURES.index("transito_na_rota")] == 0
    assert x[0, FEATURES.index("divergencia")] == 0
    assert np.isfinite(x).all()


def test_divergencia_dentro_da_tolerancia_nao_conta():
    historico = [
        _registro(id=f"B{i}", quantidade_recebida=99.0 if i % 2 else 100.0) for i in range(100)
    ]
    extrator = ExtratorFeatures().ajustar(historico)
    assert extrator.tolerancia_divergencia == pytest.approx(0.01)
    x = extrator.transformar(
        [_registro(quantidade_recebida=99.0), _registro(quantidade_recebida=80.0)]
    )
    coluna = FEATURES.index("divergencia")
    assert x[0, coluna] == 0
    assert x[1, coluna] == pytest.approx(0.19)


def test_divergencia_vale_para_falta_e_para_sobra():
    assert divergencia(_registro(quantidade_recebida=90.0)) == pytest.approx(0.1)
    assert divergencia(_registro(quantidade_recebida=110.0)) == pytest.approx(0.1)
    assert divergencia(_registro(quantidade_enviada=0.0)) == 0


def test_extrator_sem_ajustar_ou_sem_dados_falha_com_clareza():
    with pytest.raises(RuntimeError):
        ExtratorFeatures().transformar([_registro()])
    with pytest.raises(ValueError):
        ExtratorFeatures().ajustar([])


def test_mesma_semente_da_os_mesmos_scores(conjunto):
    treino, teste = separar_por_tempo(conjunto.registros)
    a = DetectorAnomalias(n_estimators=50, semente=3).treinar(treino).pontuar(teste)
    b = DetectorAnomalias(n_estimators=50, semente=3).treinar(treino).pontuar(teste)
    assert np.array_equal(a, b)


def test_limiar_segue_o_orcamento_de_atencao_no_treino(conjunto):
    treino, _ = separar_por_tempo(conjunto.registros)
    d = DetectorAnomalias(n_estimators=50, fracao_alerta=0.05, semente=1).treinar(treino)
    fracao = float((d.pontuar(treino) >= d.limiar).mean())
    assert fracao == pytest.approx(0.05, abs=0.01)


def test_nota_absurda_e_mais_estranha_que_uma_comum_da_mesma_rota(conjunto, detector):
    treino, _ = separar_por_tempo(conjunto.registros)
    comum = next(r for r in treino if r.id not in conjunto.rotulos and not r.pendente)
    absurda = replace(
        comum,
        valor=comum.valor * 50,
        emitida_em=comum.emitida_em.replace(hour=3),
        quantidade_recebida=comum.quantidade_enviada * 0.5,
    )
    scores = detector.pontuar([comum, absurda])
    assert scores[1] > scores[0]
    assert scores[1] >= detector.limiar


def test_motivo_aponta_o_que_foi_alterado(conjunto, detector):
    treino, _ = separar_por_tempo(conjunto.registros)
    comum = next(r for r in treino if r.id not in conjunto.rotulos and not r.pendente)
    faltando = replace(comum, quantidade_recebida=comum.quantidade_enviada * 0.5)
    motivos = detector.explicar(faltando)
    assert motivos[0].feature == "divergencia"
    assert "faltaram 50%" in motivos[0].texto
    assert len(motivos) <= 3


def test_motivo_de_valor_cita_a_mediana_em_reais(conjunto, detector):
    treino, _ = separar_por_tempo(conjunto.registros)
    comum = next(r for r in treino if r.id not in conjunto.rotulos and not r.pendente)
    caro = replace(comum, valor=comum.valor * 40)
    textos = " ".join(m.texto for m in detector.explicar(caro))
    assert "a mediana da rota" in textos or "por item" in textos
    assert "R$" in textos


def test_pendente_nunca_cita_transito(conjunto, detector):
    _, teste = separar_por_tempo(conjunto.registros)
    pendente = next(r for r in teste if r.pendente)
    textos = " ".join(
        m.texto for m in detector.explicar(replace(pendente, valor=pendente.valor * 40))
    )
    assert "até a entrada" not in textos


def test_analisar_so_explica_o_que_foi_sinalizado(conjunto, detector):
    _, teste = separar_por_tempo(conjunto.registros)
    resultados = detector.analisar(teste)
    assert any(r.sinalizada for r in resultados)
    assert all(bool(r.motivos) == r.sinalizada for r in resultados)


def test_detector_sem_treino_falha_com_clareza():
    d = DetectorAnomalias()
    with pytest.raises(RuntimeError):
        d.pontuar([_registro()])
    with pytest.raises(RuntimeError):
        d.contribuicoes(_registro())


def test_detector_aceita_historico_menor_que_max_samples():
    historico = [_registro(id=f"B{i}", valor=100.0 + i) for i in range(30)]
    d = DetectorAnomalias(n_estimators=10, semente=1).treinar(historico)
    assert len(d.pontuar(historico)) == 30
    assert len(d.pontuar([])) == 0


@pytest.mark.parametrize("fracao", [0, 1, -0.5])
def test_fracao_de_alerta_invalida_e_recusada(fracao):
    with pytest.raises(ValueError):
        DetectorAnomalias(fracao_alerta=fracao)


def test_corte_e_temporal(conjunto):
    treino, teste = separar_por_tempo(conjunto.registros)
    assert len(treino) + len(teste) == len(conjunto.registros)
    assert max(r.emitida_em for r in treino) <= min(r.emitida_em for r in teste)


def test_medir_conta_acertos_entre_os_k_maiores():
    registros = [_registro(id=f"T{i}") for i in range(4)]
    scores = np.array([0.9, 0.8, 0.1, 0.7])
    rotulos = {"T0": "valor_alto", "T2": "divergencia"}
    m = medir(scores, registros, rotulos, k=2)
    assert m.acertos == 1
    assert m.precisao == 0.5
    assert m.recall == 0.5
    assert m.recall_por_tipo == {"valor_alto": 1.0, "divergencia": 0.0}


def test_medir_sem_anomalias_nao_divide_por_zero():
    registros = [_registro(id=f"T{i}") for i in range(3)]
    m = medir(np.array([0.3, 0.2, 0.1]), registros, {}, k=1)
    assert (m.recall, m.precisao, m.precisao_media) == (0, 0, 0)


def test_medir_recusa_tamanhos_diferentes():
    with pytest.raises(ValueError):
        medir(np.array([0.1]), [], {}, k=1)


def test_regra_simples_da_nota_maior_a_quem_foge_em_qualquer_coluna():
    treino = np.column_stack([np.arange(100.0), np.arange(100.0) * 1000])
    teste = np.array([[50.0, 50_000.0], [500.0, 50_000.0], [50.0, 5_000_000.0]])
    scores = scores_regra_simples(treino, teste)
    assert scores[1] > scores[0]
    assert scores[2] > scores[0]


def test_nao_ha_vazamento_do_futuro_no_treino(conjunto):
    treino, teste = separar_por_tempo(conjunto.registros)
    a = DetectorAnomalias(n_estimators=30, semente=1).treinar(treino)
    alterado = [replace(r, valor=r.valor * 1_000) for r in teste]
    b = DetectorAnomalias(n_estimators=30, semente=1).treinar(treino)
    assert a.limiar == b.limiar
    assert np.array_equal(a.pontuar(alterado), b.pontuar(alterado))


def test_modelo_acha_mais_que_o_acaso(conjunto):
    avaliacao, _, _ = avaliar_conjunto(conjunto, semente=1)
    acaso = avaliacao.anomalias_teste / avaliacao.teste
    assert avaliacao.modelo.precisao > 5 * acaso


def test_demo_gera_relatorio_autocontido(tmp_path, capsys):
    saida = tmp_path / "sub" / "relatorio.html"
    assert main(["--semente", "1", "--simulacoes", "2", "--saida", str(saida)]) == 0

    html = saida.read_text(encoding="utf-8")
    assert "Dados 100% sintéticos" in html
    assert "<svg" in html
    assert "Por que chamou atenção" in html
    assert not re.search(r"""(?:src|href)=["']https?://""", html)
    assert "<script src" not in html

    terminal = capsys.readouterr().out
    assert "DADOS 100% SINTETICOS" in terminal
    assert str(saida.resolve()) in terminal


def test_demo_recusa_zero_simulacoes(tmp_path):
    with pytest.raises(SystemExit):
        main(["--simulacoes", "0", "--saida", str(tmp_path / "r.html")])
