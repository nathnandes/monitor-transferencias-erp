from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

import numpy as np

from app.anomalias.avaliacao import Avaliacao, resumir
from app.anomalias.modelo import Resultado
from app.anomalias.sintetico import (
    ROTULOS_ANOMALIA,
    TIPOS_ANOMALIA,
    ConjuntoSintetico,
    TipoAnomalia,
)

_CSS = """
:root {
  color-scheme: light;
  --fundo: #f6f6f3; --superficie: #fcfcfb; --texto: #0b0b0b; --texto-2: #52514e;
  --borda: #e3e2dc; --grade: #ecebe6; --serie-1: #2a78d6; --serie-2: #eb6834;
  --neutro: #8f8e88; --destaque: #fff3e0;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --fundo: #111110; --superficie: #1a1a19; --texto: #f0efec; --texto-2: #c3c2b7;
    --borda: #33332f; --grade: #2a2a27; --serie-1: #3987e5; --serie-2: #d95926;
    --neutro: #77766f; --destaque: #3a2a14;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --fundo: #111110; --superficie: #1a1a19; --texto: #f0efec; --texto-2: #c3c2b7;
  --borda: #33332f; --grade: #2a2a27; --serie-1: #3987e5; --serie-2: #d95926;
  --neutro: #77766f; --destaque: #3a2a14;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--fundo); color: var(--texto);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 1040px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 30px; line-height: 1.2; margin: 12px 0 8px; }
h2 { font-size: 20px; margin: 0 0 4px; }
p { margin: 0 0 12px; }
.sub { color: var(--texto-2); }
.aviso {
  display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 14px;
  font-weight: 600; background: var(--destaque);
}
section {
  background: var(--superficie); border: 1px solid var(--borda); border-radius: 8px;
  padding: 20px; margin-top: 20px;
}
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px;
margin-top: 20px; }
.tile { background: var(--superficie); border: 1px solid var(--borda); border-radius: 8px;
padding: 16px; }
.tile b { display: block; font-size: 30px; line-height: 1.2; font-variant-numeric: tabular-nums; }
.tile span { color: var(--texto-2); font-size: 14px; }
.legenda { display: flex; flex-wrap: wrap; gap: 16px; font-size: 14px; color: var(--texto-2);
margin: 8px 0; }
.legenda i { display: inline-block; width: 12px; height: 12px; border-radius: 3px;
margin-right: 6px; vertical-align: -1px; }
svg { display: block; width: 100%; height: auto; }
.rolagem svg { min-width: 620px; }
svg text { fill: var(--texto-2); font-size: 13px; }
.rolagem { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--borda);
vertical-align: top; }
th { color: var(--texto-2); font-weight: 600; }
td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td ul { margin: 0; padding-left: 16px; }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--texto-2); font-size: 14px; }
#dica {
  position: fixed; display: none; pointer-events: none; z-index: 5; max-width: 280px;
  background: var(--texto); color: var(--superficie); padding: 6px 10px; border-radius: 6px;
  font-size: 13px;
}
"""

_JS = """
const dica = document.getElementById('dica');
document.querySelectorAll('[data-dica]').forEach((alvo) => {
  alvo.addEventListener('pointermove', (e) => {
    dica.textContent = alvo.dataset.dica;
    dica.style.display = 'block';
    dica.style.left = Math.min(e.clientX + 12, innerWidth - 290) + 'px';
    dica.style.top = (e.clientY + 12) + 'px';
  });
  alvo.addEventListener('pointerleave', () => { dica.style.display = 'none'; });
});
"""


@dataclass(frozen=True)
class DadosRelatorio:
    conjunto: ConjuntoSintetico
    resultados: list[Resultado]
    limiar: float
    avaliacoes: list[Avaliacao]


def _pct(fracao: float) -> str:
    return f"{fracao * 100:.0f}%"


def _dec(numero: float) -> str:
    return f"{numero:.2f}".replace(".", ",")


def _inteiro(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


def _rotulo_tipo(tipo: TipoAnomalia | None) -> str:
    return ROTULOS_ANOMALIA[tipo] if tipo else "Sem anomalia injetada"


def _recall_por_tipo(avaliacoes: Sequence[Avaliacao], tipo: TipoAnomalia, qual: str) -> float:
    valores = [
        m.recall_por_tipo[tipo]
        for m in (getattr(a, qual) for a in avaliacoes)
        if tipo in m.recall_por_tipo
    ]
    return float(np.mean(valores)) if valores else 0.0


def _grafico_tipos(avaliacoes: Sequence[Avaliacao]) -> str:
    esquerda, largura, altura_grupo = 190, 620, 54
    topo, altura = 8, 8 + altura_grupo * len(TIPOS_ANOMALIA) + 26
    partes = [
        f'<svg viewBox="0 0 930 {altura}" role="img" '
        'aria-label="Parte de cada tipo de anomalia encontrada pelo modelo e pela regra simples">'
    ]
    for tique in (0, 25, 50, 75, 100):
        x = esquerda + largura * tique / 100
        fundo = altura - 26
        partes.append(
            f'<line x1="{x}" x2="{x}" y1="{topo}" y2="{fundo}" stroke="var(--grade)"/>'
            f'<text x="{x}" y="{fundo + 18}" text-anchor="middle">{tique}%</text>'
        )
    series = (("modelo", "Modelo", "--serie-1"), ("regra_simples", "Regra simples", "--serie-2"))
    for i, tipo in enumerate(TIPOS_ANOMALIA):
        y = topo + i * altura_grupo
        partes.append(
            f'<text x="{esquerda - 12}" y="{y + 27}" text-anchor="end">'
            f"{escape(ROTULOS_ANOMALIA[tipo])}</text>"
        )
        for j, (qual, nome, cor) in enumerate(series):
            valor = _recall_por_tipo(avaliacoes, tipo, qual)
            yb = y + 8 + j * 20
            comprimento = max(largura * valor, 2)
            dica = escape(f"{ROTULOS_ANOMALIA[tipo]}: {nome} encontra {_pct(valor)}", quote=True)
            partes.append(
                f'<g data-dica="{dica}">'
                f'<rect x="{esquerda}" y="{yb - 1}" width="{largura}" height="20" '
                'fill="transparent"/>'
                f'<rect x="{esquerda}" y="{yb}" width="{comprimento:.1f}" height="16" rx="4" '
                f'fill="var({cor})"/></g>'
            )
            if i == 0:
                partes.append(
                    f'<text x="{esquerda + comprimento + 8:.1f}" y="{yb + 13}">{nome}</text>'
                )
    partes.append("</svg>")
    return "".join(partes)


def _grafico_scores(dados: DadosRelatorio) -> str:
    scores = np.array([r.score for r in dados.resultados])
    minimo, maximo = float(scores.min()), float(scores.max())
    esquerda, largura, faixa, topo = 20, 890, 130, 26
    altura = topo + faixa + 34

    def px(score: float) -> float:
        return esquerda + largura * (score - minimo) / (maximo - minimo or 1)

    rng = np.random.default_rng(7)
    normais, injetadas = [], []
    for r in dados.resultados:
        y = topo + float(rng.uniform(4, faixa - 4))
        tipo = dados.conjunto.rotulos.get(r.registro.id)
        dica = escape(f"{r.registro.id} · score {_dec(r.score)} · {_rotulo_tipo(tipo)}", quote=True)
        if tipo:
            injetadas.append(
                f'<g data-dica="{dica}"><circle cx="{px(r.score):.1f}" cy="{y:.1f}" r="11" '
                'fill="transparent"/>'
                f'<circle cx="{px(r.score):.1f}" cy="{y:.1f}" r="6" fill="var(--serie-2)" '
                'stroke="var(--superficie)" stroke-width="2"/></g>'
            )
        else:
            normais.append(
                f'<circle data-dica="{dica}" cx="{px(r.score):.1f}" cy="{y:.1f}" r="3.5" '
                'fill="var(--neutro)" fill-opacity="0.55"/>'
            )
    x_limiar = px(dados.limiar)
    fundo = topo + faixa
    return (
        f'<svg viewBox="0 0 930 {altura}" role="img" '
        'aria-label="Score de cada transferência, com o limiar de alerta">'
        f'<line x1="{esquerda}" x2="{esquerda + largura}" y1="{fundo}" y2="{fundo}" '
        'stroke="var(--borda)"/>'
        f"{''.join(normais)}{''.join(injetadas)}"
        f'<line x1="{x_limiar:.1f}" x2="{x_limiar:.1f}" y1="{topo - 6}" y2="{fundo}" '
        'stroke="var(--texto)" stroke-width="2" stroke-dasharray="5 4"/>'
        f'<text x="{x_limiar - 8:.1f}" y="{topo - 10}" text-anchor="end">'
        f"limiar de alerta ({_dec(dados.limiar)})</text>"
        f'<text x="{esquerda}" y="{fundo + 22}">menos estranha</text>'
        f'<text x="{esquerda + largura}" y="{fundo + 22}" text-anchor="end">mais estranha</text>'
        "</svg>"
    )


def _linhas_sinalizadas(dados: DadosRelatorio) -> str:
    sinalizadas = sorted(
        (r for r in dados.resultados if r.sinalizada), key=lambda r: r.score, reverse=True
    )
    linhas = []
    for r in sinalizadas:
        motivos = "".join(f"<li>{escape(m.texto)}</li>" for m in r.motivos)
        reg = r.registro
        linhas.append(
            "<tr>"
            f'<td class="n">{_dec(r.score)}</td>'
            f"<td>{escape(reg.id)}<br><span class='sub'>"
            f"{reg.emitida_em.strftime('%d/%m %H:%M')}</span></td>"
            f"<td>{escape(reg.origem)} → {escape(reg.destino)}</td>"
            f"<td><ul>{motivos}</ul></td>"
            f"<td>{escape(_rotulo_tipo(dados.conjunto.rotulos.get(reg.id)))}</td>"
            "</tr>"
        )
    return "".join(linhas)


def _linha_metrica(nome: str, avaliacoes: Sequence[Avaliacao], qual: str) -> str:
    celulas = []
    for campo in ("precisao", "recall", "precisao_media"):
        r = resumir([getattr(getattr(a, qual), campo) for a in avaliacoes])
        celulas.append(f'<td class="n">{_dec(r.media)} ± {_dec(r.desvio)}</td>')
    return f"<tr><td>{nome}</td>{''.join(celulas)}</tr>"


def gerar_html(dados: DadosRelatorio) -> str:
    avaliacoes = dados.avaliacoes
    sinalizadas = [r for r in dados.resultados if r.sinalizada]
    achadas = sum(r.registro.id in dados.conjunto.rotulos for r in sinalizadas)
    injetadas = sum(r.registro.id in dados.conjunto.rotulos for r in dados.resultados)
    modelo = resumir([a.modelo.recall for a in avaliacoes])
    regra = resumir([a.regra_simples.recall for a in avaliacoes])
    k = avaliacoes[0].modelo.k
    teste = avaliacoes[0].teste

    tabela_tipos = "".join(
        f"<tr><td>{escape(ROTULOS_ANOMALIA[t])}</td>"
        f'<td class="n">{_pct(_recall_por_tipo(avaliacoes, t, "modelo"))}</td>'
        f'<td class="n">{_pct(_recall_por_tipo(avaliacoes, t, "regra_simples"))}</td></tr>'
        for t in TIPOS_ANOMALIA
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Detector de Anomalias</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<span class="aviso">Dados 100% sintéticos: empresas, valores e notas são inventados</span>
<h1>Detector de anomalias em transferências</h1>
<p class="sub">Um modelo não supervisionado aprende o padrão de cada rota entre as empresas
e aponta as notas que fogem dele, dizendo o motivo.</p>

<div class="tiles">
  <div class="tile"><b>{_inteiro(len(dados.resultados))}</b>
    <span>notas novas analisadas (último mês)</span></div>
  <div class="tile"><b>{len(sinalizadas)}</b><span>sinalizadas para conferência</span></div>
  <div class="tile"><b>{achadas} de {injetadas}</b>
    <span>anomalias injetadas encontradas nesta execução</span></div>
  <div class="tile"><b>{_pct(modelo.media)}</b>
    <span>encontradas em {len(avaliacoes)} simulações;
    regra simples: {_pct(regra.media)}</span></div>
</div>

<section>
  <h2>O que foi sinalizado</h2>
  <p class="sub">Cada ponto é uma nota. As laranja têm anomalia injetada, e o modelo
  não sabe disso.</p>
  <div class="legenda">
    <span><i style="background:var(--neutro)"></i>Sem anomalia injetada</span>
    <span><i style="background:var(--serie-2)"></i>Anomalia injetada</span>
  </div>
  <div class="rolagem">{_grafico_scores(dados)}</div>
</section>

<section>
  <h2>Notas para conferir</h2>
  <p class="sub">O motivo vem do próprio modelo: cada característica volta ao valor típico e
  medimos quanto o score cai. "Fora do padrão" não significa erro nem fraude.</p>
  <div class="rolagem"><table>
    <thead><tr><th class="n">Score</th><th>Nota</th><th>Rota</th><th>Por que chamou atenção</th>
      <th>Gabarito</th></tr></thead>
    <tbody>{_linhas_sinalizadas(dados)}</tbody>
  </table></div>
</section>

<section>
  <h2>O modelo vale mais que uma regra simples?</h2>
  <p class="sub">Os dois conferem as mesmas {k} notas de {teste} (2%). A regra simples olha uma
  característica por vez. Média de {len(avaliacoes)} simulações com empresas e rotas diferentes.</p>
  <div class="legenda">
    <span><i style="background:var(--serie-1)"></i>Modelo</span>
    <span><i style="background:var(--serie-2)"></i>Regra simples</span>
  </div>
  <div class="rolagem">{_grafico_tipos(avaliacoes)}</div>
  <details><summary>Ver os números</summary>
    <div class="rolagem"><table>
      <thead><tr><th>Tipo de anomalia</th><th class="n">Modelo</th>
        <th class="n">Regra simples</th></tr></thead>
      <tbody>{tabela_tipos}</tbody>
    </table></div>
  </details>
  <div class="rolagem" style="margin-top:16px"><table>
    <thead><tr><th>Média ± desvio</th><th class="n">Precisão</th><th class="n">Recall</th>
      <th class="n">Precisão média (AP)</th></tr></thead>
    <tbody>
      {_linha_metrica("Modelo (IsolationForest)", avaliacoes, "modelo")}
      {_linha_metrica("Regra simples (pior percentil)", avaliacoes, "regra_simples")}
    </tbody>
  </table></div>
</section>

<section>
  <h2>Como ler estes números</h2>
  <p>Eles mostram que o método funciona nos padrões que o gerador cria, e o gerador foi escrito
  junto com o detector. Não medem a eficácia com dados reais: isso só dá para saber com pessoas
  conferindo as notas sinalizadas.</p>
  <p>A precisão também é limitada pelo orçamento: há menos anomalias do que notas conferidas,
  então nem um modelo perfeito chegaria a 100%.</p>
</section>
</main>
<div id="dica" role="status"></div>
<script>{_JS}</script>
</body>
</html>
"""
