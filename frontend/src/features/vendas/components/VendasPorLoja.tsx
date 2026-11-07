import { formatarMoeda, formatarNumero, nomeCurtoEmpresa } from "../../../lib/format";
import type { VendasPorEmpresa } from "../../../types/api";
import { formatarPercentual, paraNumero, participacao } from "../lib/vendas";


export function VendasPorLoja({ dados }: { dados: VendasPorEmpresa[] }) {
  const total = dados.reduce((soma, e) => soma + paraNumero(e.faturamento), 0);
  const maior = Math.max(...dados.map((e) => paraNumero(e.faturamento)), 0);

  return (
    <ol className="flex flex-col divide-y divide-borda">
      {dados.map((e, i) => {
        const faturamento = paraNumero(e.faturamento);
        const largura = maior > 0 ? (faturamento / maior) * 100 : 0;
        return (
          <li key={e.empresa.codigo} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 py-3 first:pt-0 last:pb-0">
            <span className="tabular row-span-2 text-sm font-bold text-texto-mudo">{i + 1}</span>
            <p className="min-w-0 truncate text-sm font-semibold text-texto" title={e.empresa.nome}>
              <span className="tabular text-texto-mudo">{e.empresa.codigo}</span> · {nomeCurtoEmpresa(e.empresa.nome)}
            </p>
            <p className="tabular text-right text-sm font-bold text-texto">{formatarMoeda(e.faturamento)}</p>
            <div className="h-1.5 overflow-hidden rounded-sm bg-superficie-3" aria-hidden>
              <div className="h-full rounded-sm bg-texto" style={{ width: `${largura}%` }} />
            </div>
            <p className="tabular text-right text-xs text-texto-mudo">
              {formatarPercentual(participacao(faturamento, total))} · {formatarNumero(e.notas)} notas · ticket{" "}
              {formatarMoeda(e.ticket_medio)}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
