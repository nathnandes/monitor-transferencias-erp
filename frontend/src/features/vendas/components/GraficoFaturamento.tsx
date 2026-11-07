import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { ChartDataTable } from "../../../components/charts/ChartDataTable";
import { COR_EIXO, COR_GRADE, COR_ROTULO, COR_SERIE_1, CURSOR_BARRA, TICK } from "../../../components/charts/chartTheme";
import { formatarMoedaCurta, formatarNumero, formatarNumeroCurto, formatarMoedaNumero } from "../../../lib/format";
import type { PontoGrafico } from "../lib/vendas";
import { criarTooltipPonto } from "./TooltipVendas";


const MAXIMO_COM_ROTULO = 16;
export const ALTURA_GRAFICO_VENDAS = 300;

const conteudoTooltip = criarTooltipPonto<PontoGrafico>((p) => p.rotuloCompleto, COR_SERIE_1);

interface PropsRotulo {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  value?: unknown;
}


function RotuloBarra({ x = 0, y = 0, width = 0, value }: PropsRotulo) {
  return (
    <text
      x={Number(x) + Number(width) / 2}
      y={Number(y) - 6}
      textAnchor="middle"
      fill={COR_ROTULO}
      fontSize={11}
      fontWeight={600}
    >
      {formatarNumeroCurto(Number(value))}
    </text>
  );
}


const valorDaBarra = (p: PontoGrafico) => (p.devolucoes === null ? p.faturamento : p.liquido);


export function GraficoFaturamento({ dados }: { dados: PontoGrafico[] }) {

  const largo = useMediaQuery("(min-width: 640px)");
  const comRotulo = largo && dados.length <= MAXIMO_COM_ROTULO;
  return (
    <>
      <ResponsiveContainer width="100%" height={ALTURA_GRAFICO_VENDAS}>
        <BarChart data={dados} margin={{ top: comRotulo ? 24 : 8, right: 4, bottom: 0, left: 4 }}>
          <CartesianGrid vertical={false} stroke={COR_GRADE} />
          <XAxis dataKey="rotulo" tick={TICK} axisLine={{ stroke: COR_EIXO }} tickLine={false} minTickGap={8} />
          <YAxis
            tick={TICK}
            axisLine={false}
            tickLine={false}
            width={72}
            tickFormatter={(v: number) => formatarMoedaCurta(v)}
          />
          <Tooltip cursor={CURSOR_BARRA} content={conteudoTooltip} />
          <Bar dataKey={valorDaBarra} name="Faturamento" fill={COR_SERIE_1} radius={[4, 4, 0, 0]} maxBarSize={56} isAnimationActive={false}>
            {comRotulo && (
              <LabelList dataKey={valorDaBarra} content={RotuloBarra} />
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Evolução do faturamento"
        linhas={dados}
        chave={(d) => d.chave}
        colunas={[
          { titulo: "Período", valor: (d) => d.rotuloCompleto },
          { titulo: "Faturamento bruto", valor: (d) => formatarMoedaNumero(d.faturamento), numerica: true },
          {
            titulo: "Devoluções",
            valor: (d) => (d.devolucoes === null ? "—" : formatarMoedaNumero(d.devolucoes)),
            numerica: true,
          },
          { titulo: "Líquido", valor: (d) => formatarMoedaNumero(valorDaBarra(d)), numerica: true },
          { titulo: "Notas", valor: (d) => formatarNumero(d.notas), numerica: true },
        ]}
      />
    </>
  );
}
