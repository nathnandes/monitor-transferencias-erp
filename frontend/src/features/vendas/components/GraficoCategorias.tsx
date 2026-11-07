import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useMediaQuery } from "../../../hooks/useMediaQuery";
import { ChartDataTable } from "../../../components/charts/ChartDataTable";
import { COR_ROTULO, COR_SERIE_1, CURSOR_BARRA, TICK_CATEGORIA } from "../../../components/charts/chartTheme";
import { formatarMoedaCurta, formatarNumero, formatarMoedaNumero } from "../../../lib/format";
import type { VendasPorCategoria } from "../../../types/api";
import { formatarPercentual, nomeCategoria, paraNumero, participacao } from "../lib/vendas";
import { CaixaTooltipVendas } from "./TooltipVendas";

const ALTURA_POR_CATEGORIA = 38;

interface LinhaCategoria {
  categoria: string;
  nome: string;
  faturamento: number;
  quantidade: number;
  notas: number;
  percentual: number;
}

function TooltipCategoria({ active, payload }: { active?: boolean; payload?: ReadonlyArray<{ payload?: unknown }> }) {
  const linha = payload?.[0]?.payload as LinhaCategoria | undefined;
  if (!active || !linha) return null;
  return (
    <CaixaTooltipVendas
      titulo={linha.nome}
      linhas={[
        { nome: "Faturamento", valor: formatarMoedaNumero(linha.faturamento), cor: COR_SERIE_1 },
        { nome: "Participação", valor: formatarPercentual(linha.percentual) },
        { nome: "Quantidade", valor: formatarNumero(Math.round(linha.quantidade)) },
      ]}
    />
  );
}


export function GraficoCategorias({ dados }: { dados: VendasPorCategoria[] }) {

  const largo = useMediaQuery("(min-width: 640px)");
  const total = dados.reduce((soma, c) => soma + paraNumero(c.faturamento), 0);
  const linhas: LinhaCategoria[] = dados.map((c) => {
    const faturamento = paraNumero(c.faturamento);
    return {
      categoria: c.categoria,
      nome: nomeCategoria(c.categoria),
      faturamento,
      quantidade: paraNumero(c.quantidade),
      notas: c.notas,
      percentual: participacao(faturamento, total),
    };
  });

  return (
    <>
      <ResponsiveContainer width="100%" height={Math.max(200, linhas.length * ALTURA_POR_CATEGORIA + 16)}>
        <BarChart data={linhas} layout="vertical" margin={{ top: 4, right: largo ? 72 : 60, bottom: 4, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="nome" width={largo ? 168 : 104} tick={TICK_CATEGORIA} axisLine={false} tickLine={false} />
          <Tooltip cursor={CURSOR_BARRA} content={TooltipCategoria} />
          <Bar dataKey="faturamento" name="Faturamento" fill={COR_SERIE_1} radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
            <LabelList
              dataKey="faturamento"
              position="right"
              fill={COR_ROTULO}
              fontSize={11}
              fontWeight={600}
              formatter={(v: unknown) => formatarMoedaCurta(Number(v))}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <ChartDataTable
        legenda="Vendas por categoria"
        linhas={linhas}
        chave={(l) => l.categoria}
        colunas={[
          { titulo: "Categoria", valor: (l) => l.nome },
          { titulo: "Faturamento", valor: (l) => formatarMoedaNumero(l.faturamento), numerica: true },
          { titulo: "Participação", valor: (l) => formatarPercentual(l.percentual), numerica: true },
          { titulo: "Quantidade", valor: (l) => formatarNumero(Math.round(l.quantidade)), numerica: true },
        ]}
      />
    </>
  );
}
