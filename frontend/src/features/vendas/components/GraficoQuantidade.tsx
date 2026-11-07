import { Area, AreaChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { ChartDataTable } from "../../../components/charts/ChartDataTable";
import {
  COR_EIXO,
  COR_GRADE,
  COR_ROTULO,
  COR_SERIE_2,
  COR_SUPERFICIE,
  COR_TICK_FORTE,
  TICK,
} from "../../../components/charts/chartTheme";
import { formatarNumero, formatarNumeroCurto } from "../../../lib/format";
import type { PontoGrafico } from "../lib/vendas";
import { ALTURA_GRAFICO_VENDAS } from "./GraficoFaturamento";
import { criarTooltipPonto } from "./TooltipVendas";

const MAXIMO_COM_ROTULO = 16;

const conteudoTooltip = criarTooltipPonto<PontoGrafico>((p) => p.rotuloCompleto, COR_SERIE_2);


export function GraficoQuantidade({ dados }: { dados: PontoGrafico[] }) {

  const largo = useMediaQuery("(min-width: 640px)");
  const comRotulo = largo && dados.length <= MAXIMO_COM_ROTULO;
  return (
    <>
      <ResponsiveContainer width="100%" height={ALTURA_GRAFICO_VENDAS}>
        <AreaChart data={dados} margin={{ top: comRotulo ? 24 : 8, right: 16, bottom: 0, left: 4 }}>
          <defs>
            <linearGradient id="grad-quantidade-vendida" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={COR_SERIE_2} stopOpacity={0.3} />
              <stop offset="100%" stopColor={COR_SERIE_2} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke={COR_GRADE} />
          <XAxis dataKey="rotulo" tick={TICK} axisLine={{ stroke: COR_EIXO }} tickLine={false} minTickGap={8} padding={{ left: 28, right: 28 }} />
          <YAxis tick={TICK} axisLine={false} tickLine={false} width={56} tickFormatter={(v: number) => formatarNumeroCurto(v)} />
          <Tooltip cursor={{ stroke: COR_TICK_FORTE, strokeWidth: 1, strokeDasharray: "3 3" }} content={conteudoTooltip} />
          <Area
            type="linear"
            dataKey="quantidade"
            name="Quantidade vendida"
            stroke={COR_SERIE_2}
            strokeWidth={2.5}
            fill="url(#grad-quantidade-vendida)"
            dot={{ r: 3, fill: COR_SERIE_2, stroke: COR_SUPERFICIE, strokeWidth: 2 }}
            activeDot={{ r: 5, stroke: COR_SUPERFICIE, strokeWidth: 2, fill: COR_SERIE_2 }}
            isAnimationActive={false}
          >
            {comRotulo && (
              <LabelList
                dataKey="quantidade"
                position="top"
                offset={10}
                fill={COR_ROTULO}
                fontSize={11}
                fontWeight={600}
                formatter={(v: unknown) => formatarNumeroCurto(Number(v))}
              />
            )}
          </Area>
        </AreaChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Quantidade vendida"
        linhas={dados}
        chave={(d) => d.chave}
        colunas={[
          { titulo: "Período", valor: (d) => d.rotuloCompleto },
          { titulo: "Quantidade", valor: (d) => formatarNumero(Math.round(d.quantidade)), numerica: true },
        ]}
      />
    </>
  );
}
