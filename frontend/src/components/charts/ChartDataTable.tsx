import { Table2 } from "lucide-react";
import type { ReactNode } from "react";

import { formatarNumero } from "../../lib/format";

export interface ColunaTabela<T> {
  titulo: string;
  valor: (linha: T) => ReactNode;
  numerica?: boolean;
}

interface ChartDataTableProps<T> {
  legenda: string;
  linhas: T[];
  colunas: ColunaTabela<T>[];
  chave: (linha: T) => string;
}


export function ChartDataTable<T>({ legenda, linhas, colunas, chave }: ChartDataTableProps<T>) {
  return (
    <details className="group mt-3 text-xs">
      <summary className="inline-flex cursor-pointer select-none items-center gap-1.5 rounded py-1 text-texto-mudo hover:text-acento-texto">
        <Table2 aria-hidden className="size-3.5" />
        <span className="group-open:hidden">Ver dados em tabela</span>
        <span className="hidden group-open:inline">Ocultar tabela</span>
      </summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-md border border-borda">
        <table className="w-full text-left">
          <caption className="sr-only">{legenda}</caption>
          <thead className="sticky top-0 bg-superficie-2 text-texto-mudo">
            <tr>
              {colunas.map((c) => (
                <th key={c.titulo} scope="col" className={`px-3 py-1.5 font-medium ${c.numerica ? "text-right" : ""}`}>
                  {c.titulo}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="tabular text-texto-2">
            {linhas.map((linha) => (
              <tr key={chave(linha)} className="border-t border-borda">
                {colunas.map((c) => {
                  const v = c.valor(linha);
                  return (
                    <td key={c.titulo} className={`px-3 py-1.5 ${c.numerica ? "text-right" : ""}`}>
                      {typeof v === "number" ? formatarNumero(v) : v}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
