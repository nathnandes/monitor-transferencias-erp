import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ContagemEmpresa } from "../../lib/aggregations";
import { ChartDataTable } from "./ChartDataTable";
import { COR_EIXO, COR_GRADE, COR_SERIE_1, COR_SERIE_2, CURSOR_BARRA, TICK, TICK_CATEGORIA } from "./chartTheme";
import { criarTooltip, type ItemPayload } from "./ChartTooltip";

const ALTURA_POR_EMPRESA = 44;
const ALTURA_MINIMA = 220;

const conteudoTooltip = criarTooltip(
  (_codigo, dados) => {
    const e = dados as ContagemEmpresa;
    return `${e.codigo} — ${e.nome}`;
  },
  (item: ItemPayload) => String(item.fill ?? item.color ?? COR_SERIE_1),
);


export function CompanyChart({ dados }: { dados: ContagemEmpresa[] }) {
  const altura = Math.max(ALTURA_MINIMA, dados.length * ALTURA_POR_EMPRESA + 60);

  return (
    <>
      <ResponsiveContainer width="100%" height={altura}>
        <BarChart data={dados} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }} barGap={2}>
          <CartesianGrid horizontal={false} stroke={COR_GRADE} />
          <XAxis type="number" allowDecimals={false} tick={TICK} axisLine={{ stroke: COR_EIXO }} tickLine={false} />
          <YAxis type="category" dataKey="codigo" width={40} tick={TICK_CATEGORIA} axisLine={false} tickLine={false} />
          <Tooltip cursor={CURSOR_BARRA} content={conteudoTooltip} />
          <Legend
            verticalAlign="top"
            align="right"
            height={28}
            iconType="square"
            iconSize={10}
            itemSorter={null}
            formatter={(valor) => <span className="text-xs text-texto-2">{valor}</span>}
          />
          <Bar dataKey="saidas" name="Saídas (origem)" fill={COR_SERIE_1} radius={[0, 4, 4, 0]} maxBarSize={14} fillOpacity={0.85} isAnimationActive={false} />
          <Bar dataKey="entradas" name="Entradas (destino)" fill={COR_SERIE_2} radius={[0, 4, 4, 0]} maxBarSize={14} fillOpacity={0.85} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Transferências por empresa"
        linhas={dados}
        chave={(d) => d.codigo}
        colunas={[
          { titulo: "Empresa", valor: (d) => `${d.codigo} — ${d.nome}` },
          { titulo: "Saídas (origem)", valor: (d) => d.saidas, numerica: true },
          { titulo: "Entradas (destino)", valor: (d) => d.entradas, numerica: true },
        ]}
      />
    </>
  );
}
