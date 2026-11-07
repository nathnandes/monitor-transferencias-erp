import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ContagemSeveridade } from "../../lib/aggregations";
import { ChartDataTable } from "./ChartDataTable";
import {
  ALTURA_PADRAO,
  COR_EIXO,
  COR_GRADE,
  COR_ROTULO,
  CURSOR_BARRA,
  TICK,
  TICK_CATEGORIA,
  corDaSeveridade,
} from "./chartTheme";
import { criarTooltip, type ItemPayload } from "./ChartTooltip";

const conteudoTooltip = criarTooltip(
  (severidade) => severidade,
  (item: ItemPayload) => corDaSeveridade((item.payload as ContagemSeveridade).severidade),
);


export function SeverityChart({ dados }: { dados: ContagemSeveridade[] }) {
  return (
    <>
      <ResponsiveContainer width="100%" height={ALTURA_PADRAO}>
        <BarChart data={dados} margin={{ top: 20, right: 8, bottom: 4, left: -16 }}>
          <CartesianGrid vertical={false} stroke={COR_GRADE} />
          <XAxis dataKey="severidade" tick={TICK_CATEGORIA} axisLine={{ stroke: COR_EIXO }} tickLine={false} />
          <YAxis allowDecimals={false} tick={TICK} axisLine={false} tickLine={false} />
          <Tooltip cursor={CURSOR_BARRA} content={conteudoTooltip} />
          <Bar dataKey="total" name="Eventos" radius={[4, 4, 0, 0]} maxBarSize={56} fillOpacity={0.85} isAnimationActive={false}>
            {dados.map((d) => (
              <Cell key={d.severidade} fill={corDaSeveridade(d.severidade)} />
            ))}
            <LabelList dataKey="total" position="top" fill={COR_ROTULO} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Eventos por severidade"
        linhas={dados}
        chave={(d) => d.severidade}
        colunas={[
          { titulo: "Severidade", valor: (d) => d.severidade },
          { titulo: "Eventos", valor: (d) => d.total, numerica: true },
        ]}
      />
    </>
  );
}
