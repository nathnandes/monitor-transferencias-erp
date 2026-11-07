import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { COR_SUPERFICIE } from "../../../components/charts/chartTheme";
import { formatarMoedaCurta, formatarNumero, formatarMoedaNumero } from "../../../lib/format";
import type { FormaPagamento } from "../../../types/api";
import { formatarPercentual, nomeCategoria, paraNumero, participacao } from "../lib/vendas";
import { CaixaTooltipVendas } from "./TooltipVendas";


const PALETA = [
  "#1f2933",
  "#2f6fde",
  "#e2b400",
  "#16a34a",
  "#ec835a",
  "#7c3aed",
  "#0891b2",
  "#db2777",
  "#65a30d",
  "#92400e",
  "#64748b",
  "#b8bec8",
];

interface Fatia {
  forma: string;
  nome: string;
  valor: number;
  parcelas: number;
  percentual: number;
  cor: string;
}

function TooltipForma({ active, payload }: { active?: boolean; payload?: ReadonlyArray<{ payload?: unknown }> }) {
  const fatia = payload?.[0]?.payload as Fatia | undefined;
  if (!active || !fatia) return null;
  return (
    <CaixaTooltipVendas
      titulo={fatia.nome}
      linhas={[
        { nome: "Recebido", valor: formatarMoedaNumero(fatia.valor), cor: fatia.cor },
        { nome: "Participação", valor: formatarPercentual(fatia.percentual) },
        { nome: "Parcelas", valor: formatarNumero(fatia.parcelas) },
      ]}
    />
  );
}


export function GraficoFormasPagamento({ dados }: { dados: FormaPagamento[] }) {
  const total = dados.reduce((soma, f) => soma + paraNumero(f.valor), 0);
  const fatias: Fatia[] = dados.map((f, i) => ({
    forma: f.forma,
    nome: nomeCategoria(f.forma),
    valor: paraNumero(f.valor),
    parcelas: f.parcelas,
    percentual: participacao(paraNumero(f.valor), total),
    cor: PALETA[i % PALETA.length] ?? "#b8bec8",
  }));

  return (
    <div className="flex flex-col gap-5">
      <div className="relative mx-auto aspect-square w-full max-w-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={fatias}
              dataKey="valor"
              nameKey="nome"
              innerRadius="62%"
              outerRadius="100%"
              paddingAngle={fatias.length > 1 ? 1.5 : 0}
              stroke={COR_SUPERFICIE}
              strokeWidth={2}
              isAnimationActive={false}
            >
              {fatias.map((f) => (
                <Cell key={f.forma} fill={f.cor} />
              ))}
            </Pie>
            <Tooltip content={TooltipForma} />
          </PieChart>
        </ResponsiveContainer>
        <div aria-hidden className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <p className="text-[11px] font-medium text-texto-mudo">Recebido</p>
            <p className="tabular font-display text-lg font-bold text-texto">{formatarMoedaCurta(total)}</p>
          </div>
        </div>
      </div>
      <ul className="flex flex-col gap-2.5">
        {fatias.map((f) => (
          <li key={f.forma} className="flex items-center gap-3 text-sm">
            <span aria-hidden className="size-3 shrink-0 rounded-sm" style={{ background: f.cor }} />
            <span className="min-w-0 flex-1 truncate text-texto" title={f.forma}>
              {f.nome}
            </span>
            <span className="tabular text-xs text-texto-mudo">{formatarMoedaNumero(f.valor)}</span>
            <span className="tabular w-12 text-right font-bold text-texto">{formatarPercentual(f.percentual)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
