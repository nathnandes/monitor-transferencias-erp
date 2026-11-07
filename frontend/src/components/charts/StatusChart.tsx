import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ContagemStatus } from "../../lib/aggregations";
import { ChartDataTable } from "./ChartDataTable";
import {
  ALTURA_PADRAO,
  COR_EIXO,
  COR_GRADE,
  COR_ROTULO,
  CURSOR_BARRA,
  TICK,
  TICK_CATEGORIA,
  corDoStatus,
} from "./chartTheme";
import { criarTooltip, type ItemPayload } from "./ChartTooltip";

function percentual(parte: number, total: number): string {
  return total ? `${Math.round((parte / total) * 100)}%` : "—";
}

const conteudoTooltip = criarTooltip(
  (status) => status,
  (item: ItemPayload) => corDoStatus((item.payload as ContagemStatus).status),
);


export function StatusChart({ dados }: { dados: ContagemStatus[] }) {
  const total = dados.reduce((soma, d) => soma + d.total, 0);

  return (
    <>
      <ResponsiveContainer width="100%" height={ALTURA_PADRAO}>
        <BarChart data={dados} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 8 }}>
          <CartesianGrid horizontal={false} stroke={COR_GRADE} />
          <XAxis type="number" allowDecimals={false} tick={TICK} axisLine={{ stroke: COR_EIXO }} tickLine={false} />
          <YAxis type="category" dataKey="status" width={100} tick={TICK_CATEGORIA} axisLine={false} tickLine={false} />
          <Tooltip cursor={CURSOR_BARRA} content={conteudoTooltip} />
          <Bar dataKey="total" name="Transferências" radius={[0, 4, 4, 0]} maxBarSize={24} fillOpacity={0.85} isAnimationActive={false}>
            {dados.map((d) => (
              <Cell key={d.status} fill={corDoStatus(d.status)} />
            ))}
            <LabelList dataKey="total" position="right" fill={COR_ROTULO} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Transferências por status"
        linhas={dados}
        chave={(d) => d.status}
        colunas={[
          { titulo: "Status", valor: (d) => d.status },
          { titulo: "Transferências", valor: (d) => d.total, numerica: true },
          { titulo: "% do total", valor: (d) => percentual(d.total, total), numerica: true },
        ]}
      />
    </>
  );
}
