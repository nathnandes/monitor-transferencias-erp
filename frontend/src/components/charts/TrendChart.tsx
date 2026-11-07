import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Granularidade, PontoSerie } from "../../lib/aggregations";
import { ChartDataTable } from "./ChartDataTable";
import { ALTURA_PADRAO, COR_EIXO, COR_GRADE, COR_SERIE_1, COR_SUPERFICIE, COR_TICK_FORTE, TICK } from "./chartTheme";
import { criarTooltip } from "./ChartTooltip";

const conteudoTooltip = criarTooltip(
  (_chave, dados) => (dados as PontoSerie).rotuloCompleto,
  () => COR_SERIE_1,
);


export function TrendChart({ dados }: { dados: PontoSerie[] }) {

  const poucosPontos = dados.length <= 1;

  return (
    <>
      <ResponsiveContainer width="100%" height={ALTURA_PADRAO}>
        <AreaChart data={dados} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
          <defs>
            <linearGradient id="grad-evolucao" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COR_SERIE_1} stopOpacity={0.35} />
              <stop offset="100%" stopColor={COR_SERIE_1} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke={COR_GRADE} />
          <XAxis dataKey="rotulo" tick={TICK} axisLine={{ stroke: COR_EIXO }} tickLine={false} minTickGap={24} />
          <YAxis allowDecimals={false} tick={TICK} axisLine={false} tickLine={false} />
          <Tooltip cursor={{ stroke: COR_TICK_FORTE, strokeWidth: 1, strokeDasharray: "3 3" }} content={conteudoTooltip} />
          <Legend
            verticalAlign="top"
            align="right"
            height={28}
            iconType="plainline"
            iconSize={14}
            formatter={(valor) => <span className="text-xs text-texto-2">{valor}</span>}
          />
          <Area
            type="linear"
            dataKey="total"
            name="Transferências criadas"
            stroke={COR_SERIE_1}
            strokeWidth={2}
            fill="url(#grad-evolucao)"
            dot={poucosPontos ? { r: 4, fill: COR_SERIE_1, stroke: COR_SUPERFICIE, strokeWidth: 2 } : false}
            activeDot={{ r: 5, stroke: COR_SUPERFICIE, strokeWidth: 2, fill: COR_SERIE_1 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Evolução das transferências"
        linhas={dados}
        chave={(d) => d.chave}
        colunas={[
          { titulo: "Período", valor: (d) => d.rotuloCompleto },
          { titulo: "Transferências criadas", valor: (d) => d.total, numerica: true },
        ]}
      />
    </>
  );
}

const OPCOES: { valor: Granularidade; rotulo: string }[] = [
  { valor: "dia", rotulo: "Dia" },
  { valor: "semana", rotulo: "Semana" },
];

interface GranularidadeToggleProps {
  valor: Granularidade;
  aoMudar: (valor: Granularidade) => void;
}


export function GranularidadeToggle({ valor, aoMudar }: GranularidadeToggleProps) {
  return (
    <div role="group" aria-label="Agrupar por" className="inline-flex rounded-lg border border-borda-forte bg-superficie-2 p-0.5">
      {OPCOES.map((o) => (
        <button
          key={o.valor}
          type="button"
          aria-pressed={valor === o.valor}
          onClick={() => aoMudar(o.valor)}
          className="h-8 rounded-md px-3 text-xs font-medium text-texto-2 hover:text-texto aria-pressed:bg-texto aria-pressed:font-semibold aria-pressed:text-superficie sm:h-7"
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}
