import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { COR_SUPERFICIE } from "../../../components/charts/chartTheme";
import { formatarNumero, formatarMoedaNumero } from "../../../lib/format";
import type { CanalVenda, VendasPorCanal } from "../../../types/api";
import { formatarPercentual, paraNumero, participacao } from "../lib/vendas";
import { CaixaTooltipVendas } from "./TooltipVendas";


export const COR_CANAL: Record<CanalVenda, string> = {
  faturamento: "#1f2933",
  televendas: "#2f6fde",
  balcao: "#e2b400",
};

interface FatiaCanal {
  canal: CanalVenda;
  rotulo: string;
  faturamento: number;
  notas: number;
  percentual: number;
}

function TooltipCanal({ active, payload }: { active?: boolean; payload?: ReadonlyArray<{ payload?: unknown }> }) {
  const fatia = payload?.[0]?.payload as FatiaCanal | undefined;
  if (!active || !fatia) return null;
  return (
    <CaixaTooltipVendas
      titulo={fatia.rotulo}
      linhas={[
        { nome: "Faturamento", valor: formatarMoedaNumero(fatia.faturamento), cor: COR_CANAL[fatia.canal] },
        { nome: "Participação", valor: formatarPercentual(fatia.percentual) },
        { nome: "Notas", valor: formatarNumero(fatia.notas) },
      ]}
    />
  );
}


export function GraficoCanais({ dados }: { dados: VendasPorCanal[] }) {
  const total = dados.reduce((soma, c) => soma + paraNumero(c.faturamento), 0);
  const fatias: FatiaCanal[] = dados.map((c) => ({
    canal: c.canal,
    rotulo: c.rotulo,
    faturamento: paraNumero(c.faturamento),
    notas: c.notas,
    percentual: participacao(paraNumero(c.faturamento), total),
  }));

  return (
    <div className="flex flex-col gap-5">
      <div className="relative mx-auto aspect-square w-full max-w-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={fatias}
              dataKey="faturamento"
              nameKey="rotulo"
              innerRadius="62%"
              outerRadius="100%"
              paddingAngle={fatias.length > 1 ? 2 : 0}
              stroke={COR_SUPERFICIE}
              strokeWidth={2}
              isAnimationActive={false}
            >
              {fatias.map((f) => (
                <Cell key={f.canal} fill={COR_CANAL[f.canal]} />
              ))}
            </Pie>
            <Tooltip content={TooltipCanal} />
          </PieChart>
        </ResponsiveContainer>
        <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <p className="text-[11px] font-medium text-texto-mudo">Notas</p>
            <p className="tabular font-display text-xl font-bold text-texto">
              {formatarNumero(fatias.reduce((s, f) => s + f.notas, 0))}
            </p>
          </div>
        </div>
      </div>
      <ul className="flex flex-col gap-3">
        {fatias.map((f) => (
          <li key={f.canal} className="flex items-start gap-3">
            <span aria-hidden className="mt-1 size-3 shrink-0 rounded-sm" style={{ background: COR_CANAL[f.canal] }} />
            <div className="min-w-0 flex-1">
              <p className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-semibold text-texto">{f.rotulo}</span>
                <span className="tabular font-bold text-texto">{formatarPercentual(f.percentual)}</span>
              </p>
              <p className="tabular flex justify-between gap-3 text-xs text-texto-mudo">
                <span>{formatarMoedaNumero(f.faturamento)}</span>
                <span>{formatarNumero(f.notas)} notas</span>
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
