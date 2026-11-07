import { Eye } from "lucide-react";
import type { ReactNode } from "react";

import { formatarMoeda, formatarQuantidade } from "../../../lib/format";
import type { Decimal, ItemEstoque } from "../../../types/api";
import { CelulaCobertura } from "./CoberturaEstoque";
import { CodigoProduto } from "./CodigoProduto";

interface EstoqueTabelaProps {
  itens: ItemEstoque[];

  porEmpresa: boolean;

  janelaDias?: number;

  comCobertura?: boolean;
  carregando?: boolean;
  aoAbrir: (item: ItemEstoque) => void;

  acaoExtra?: (item: ItemEstoque) => ReactNode;
}


function Rotulo({ children }: { children: ReactNode }) {
  return (
    <span aria-hidden className="mb-0.5 block text-[11px] font-medium uppercase tracking-wide text-texto-mudo md:hidden">
      {children}
    </span>
  );
}

export function eNegativo(valor: Decimal | null): boolean {
  return valor !== null && valor.trim().startsWith("-");
}


export function Quantidade({ valor, forte = false }: { valor: Decimal | null; forte?: boolean }) {
  const cor = eNegativo(valor) ? "text-critico-texto" : forte ? "text-texto" : "text-texto-2";
  return <span className={`${cor} ${forte ? "font-semibold" : ""}`}>{formatarQuantidade(valor)}</span>;
}


export function faixaDePreco(min: Decimal | null, max: Decimal | null): string {
  if (min === null || max === null || Number(min) === Number(max)) return formatarMoeda(min ?? max);
  return `${formatarMoeda(min)} – ${formatarMoeda(max)}`;
}


function OrigemProduto({ item }: { item: ItemEstoque }) {
  if (!item.fabricante && !item.fornecedor) return null;
  return (
    <span className="block text-[11px] text-texto-mudo">
      {item.fabricante && <span title="Fabricante (marca do cadastro)">{item.fabricante}</span>}
      {item.fabricante && item.fornecedor && " · "}
      {item.fornecedor && <span title="Fornecedor da última compra">comprado de {item.fornecedor}</span>}
    </span>
  );
}

const TH = "px-3 py-2.5 font-semibold";
const TD = "md:px-3 md:py-2.5";


export function EstoqueTabela({
  itens,
  porEmpresa,
  janelaDias,
  comCobertura = true,
  carregando = false,
  aoAbrir,
  acaoExtra,
}: EstoqueTabelaProps) {
  const rotuloVenda = janelaDias ? `Venda/dia (${janelaDias}d)` : "Venda/dia";
  return (
    <div
      aria-busy={carregando}
      className={`transition-opacity md:max-h-[70vh] md:overflow-auto md:rounded-lg md:border md:border-borda ${carregando ? "opacity-60" : ""}`}
    >
      <table role="table" className="w-full text-left text-sm max-md:block">
        <caption className="sr-only">Estoque por produto, página atual</caption>
        <thead role="rowgroup" className="max-md:sr-only md:sticky md:top-0 md:z-10">
          <tr role="row" className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo shadow-[inset_0_-1px_0_var(--color-borda)]">
            <th role="columnheader" scope="col" className={TH}>Produto</th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Saldo atual</th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Reservado</th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Disponível</th>
            {comCobertura && (
              <>
                <th role="columnheader" scope="col" className={`${TH} text-right`}>{rotuloVenda}</th>
                <th role="columnheader" scope="col" className={`${TH} text-right`}>Cobertura</th>
              </>
            )}
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Preço varejo</th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>
              {porEmpresa ? "Custo" : "Custo médio"}
            </th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Valor (custo)</th>
            {!porEmpresa && (
              <th role="columnheader" scope="col" className={`${TH} text-right`}>Empresas com saldo</th>
            )}
            <th role="columnheader" scope="col" className="px-3 py-2.5"><span className="sr-only">Ações</span></th>
          </tr>
        </thead>
        <tbody role="rowgroup" className="tabular max-md:grid max-md:gap-3">
          {itens.map((item) => (
            <tr
              key={`${item.id_produto}/${item.id_subproduto}`}
              role="row"
              className="text-texto-2 transition-colors max-md:grid max-md:grid-cols-3 max-md:gap-x-4 max-md:gap-y-3 max-md:rounded-lg max-md:border max-md:border-borda max-md:bg-superficie-2/40 max-md:p-3 md:border-b md:border-borda/70 md:hover:bg-superficie-2"
            >
              <td role="cell" className={`max-md:col-span-3 ${TD}`}>
                <Rotulo>Produto</Rotulo>
                <CodigoProduto idProduto={item.id_produto} idSubproduto={item.id_subproduto} />
                {item.descricao && <span className="block text-xs text-texto-mudo">{item.descricao}</span>}
                <OrigemProduto item={item} />
              </td>
              <td role="cell" className={`md:text-right ${TD}`}>
                <Rotulo>Atual</Rotulo>
                <Quantidade valor={item.saldo_atual} forte />
              </td>
              <td role="cell" className={`md:text-right ${TD}`}>
                <Rotulo>Reservado</Rotulo>
                <Quantidade valor={item.saldo_reservado} />
              </td>
              <td role="cell" className={`md:text-right ${TD}`}>
                <Rotulo>Disponível</Rotulo>
                <Quantidade valor={item.saldo_disponivel} forte />
              </td>
              {comCobertura && (
                <>
                  <td role="cell" className={`md:text-right ${TD}`}>
                    <Rotulo>{rotuloVenda}</Rotulo>
                    <Quantidade valor={item.venda_media_diaria} />
                  </td>
                  <td role="cell" className={`max-md:col-span-2 md:text-right ${TD}`}>
                    <Rotulo>Cobertura</Rotulo>
                    <CelulaCobertura item={item} />
                  </td>
                </>
              )}
              <td role="cell" className={`whitespace-nowrap md:text-right ${TD}`}>
                <Rotulo>Preço varejo</Rotulo>
                {faixaDePreco(item.preco_varejo_min, item.preco_varejo_max)}
              </td>
              <td role="cell" className={`whitespace-nowrap md:text-right ${TD}`}>
                <Rotulo>{porEmpresa ? "Custo" : "Custo médio"}</Rotulo>
                {formatarMoeda(item.custo_gerencial)}
              </td>
              <td role="cell" className={`whitespace-nowrap md:text-right ${TD}`}>
                <Rotulo>Valor (custo)</Rotulo>
                <span className={eNegativo(item.valor_custo) ? "text-critico-texto" : "text-texto"}>
                  {formatarMoeda(item.valor_custo)}
                </span>
              </td>
              {!porEmpresa && (
                <td role="cell" className={`md:text-right ${TD}`}>
                  <Rotulo>Empresas com saldo</Rotulo>
                  {item.empresas_com_estoque}
                </td>
              )}
              <td role="cell" className={`max-md:col-span-3 md:whitespace-nowrap md:text-right ${TD}`}>
                {acaoExtra?.(item)}
                <button
                  type="button"
                  onClick={() => aoAbrir(item)}
                  className="btn btn-sm btn-fantasma max-md:w-full"
                  aria-label={`Ver estoque do produto ${item.id_subproduto} por empresa`}
                >
                  <Eye aria-hidden className="size-4" />
                  <span>Por empresa</span>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
