import { formatarMoeda, formatarQuantidade } from "../../../lib/format";
import type { ProdutoVendido } from "../../../types/api";

const CELULA = "px-3 py-2.5";


export function ProdutosMaisVendidos({ dados }: { dados: ProdutoVendido[] }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[32rem] text-sm">
        <thead>
          <tr className="border-b border-borda text-left text-[11px] font-semibold uppercase tracking-wide text-texto-mudo">
            <th scope="col" className={`${CELULA} w-10`}>
              #
            </th>
            <th scope="col" className={CELULA}>
              Produto
            </th>
            <th scope="col" className={`${CELULA} text-right`}>
              Quantidade
            </th>
            <th scope="col" className={`${CELULA} text-right`}>
              Faturamento
            </th>
          </tr>
        </thead>
        <tbody>
          {dados.map((p, i) => (
            <tr key={`${p.id_produto}/${p.id_subproduto ?? ""}`} className="border-b border-borda/70 last:border-0 hover:bg-superficie-2">
              <td className={`${CELULA} tabular font-bold text-texto-mudo`}>{i + 1}</td>
              <td className={CELULA}>
                <p className="font-medium text-texto">{p.descricao ?? "Sem descrição"}</p>
                <p className="tabular text-xs text-texto-mudo">
                  Cód. {p.id_subproduto ?? p.id_produto}
                  {p.id_subproduto && p.id_subproduto !== p.id_produto && ` · grade ${p.id_produto}`}
                </p>
              </td>
              <td className={`${CELULA} tabular text-right text-texto-2`}>{formatarQuantidade(p.quantidade)}</td>
              <td className={`${CELULA} tabular text-right font-semibold text-texto`}>{formatarMoeda(p.faturamento)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
