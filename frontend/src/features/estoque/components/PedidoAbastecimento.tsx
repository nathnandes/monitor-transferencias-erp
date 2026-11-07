import { PackageCheck } from "lucide-react";
import { Fragment, useId, useState } from "react";

import { BotaoExportar } from "../../../components/ui/BotaoExportar";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { useAsync } from "../../../hooks/useAsync";
import { formatarNumero, formatarQuantidade } from "../../../lib/format";
import { getPedidoAbastecimento } from "../../../services/estoqueService";
import type {
  EmpresaResumo,
  ItemPedidoAbastecimento,
} from "../../../types/api";
import { formatarCobertura, SeloCobertura } from "./CoberturaEstoque";
import type { ProdutoSelecionado } from "./ProdutoEstoqueDetalhe";


const ALVOS = [15, 30, 45, 60] as const;
const ALVO_PADRAO = 30;
const SEM_MARCA = "Sem marca";

interface PedidoAbastecimentoProps {
  loja: EmpresaResumo;

  janelaDias?: number;

  recarga: number;
  aoAbrirProduto: (produto: ProdutoSelecionado) => void;
}


function porMarca(
  itens: ItemPedidoAbastecimento[],
): [string, ItemPedidoAbastecimento[]][] {
  const grupos = new Map<string, ItemPedidoAbastecimento[]>();
  for (const item of itens) {
    const marca = item.marca ?? SEM_MARCA;
    grupos.set(marca, [...(grupos.get(marca) ?? []), item]);
  }
  return [...grupos];
}

const TH =
  "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-texto-mudo";


export function PedidoAbastecimento({
  loja,
  janelaDias,
  recarga,
  aoAbrirProduto,
}: PedidoAbastecimentoProps) {
  const [aberto, setAberto] = useState(false);
  const [alvo, setAlvo] = useState<number>(ALVO_PADRAO);
  const [origem, setOrigem] = useState("");
  const [marca, setMarca] = useState("");
  const ids = { alvo: useId(), marca: useId(), painel: useId() };
  const pedido = useAsync(
    (s) =>
      aberto
        ? getPedidoAbastecimento(loja.codigo, alvo, janelaDias, s)
        : Promise.resolve(null),
    [aberto, loja.codigo, alvo, janelaDias],
    recarga,
  );

  const dados = pedido.data;
  const abas =
    dados?.pedidos.map((p) => ({
      valor: p.deposito.codigo,
      titulo: `${p.deposito.codigo} - ${p.deposito.nome}`,
      itens: p.itens,
    })) ?? [];
  const atual = abas.find((a) => a.valor === origem) ?? abas[0];
  const grupos = atual ? porMarca(atual.itens) : [];
  const visiveis = grupos.filter(([m]) => !marca || m === marca);

  const trocarOrigem = (valor: string) => {
    setOrigem(valor);
    setMarca("");
  };

  return (
    <details
      className="rounded-md border border-borda"
      open={aberto}
      onToggle={(e) => setAberto((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer bg-superficie-2 px-3 py-2 text-sm font-semibold text-texto">
        Pedido de abastecimento
        <span className="ml-2 font-normal text-texto-mudo">
          o que falta em {loja.nome}, separado pelo depósito que tem e por marca
        </span>
      </summary>
      <div className="flex flex-col gap-3 border-t border-borda p-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div className="flex items-center gap-2">
            <label
              htmlFor={ids.alvo}
              className="text-xs font-medium text-texto-2"
            >
              Cobrir
            </label>
            <select
              id={ids.alvo}
              value={alvo}
              onChange={(ev) => setAlvo(Number(ev.target.value))}
              className="campo w-32"
            >
              {ALVOS.map((d) => (
                <option key={d} value={d}>
                  {d} dias
                </option>
              ))}
            </select>
          </div>
          <p className="text-[11px] text-texto-mudo">
            Ruptura, crítica e baixa da loja (sem as exceções). Quantidade = o
            que falta para a loja vender {alvo} dias; sai do depósito com mais
            saldo e, se não der, o resto do outro.
          </p>
        </div>

        {pedido.error ? (
          <ErrorState
            titulo="Falha ao montar o pedido"
            erro={pedido.error}
            aoTentarNovamente={pedido.recarregar}
          />
        ) : !dados ? (
          <LoadingState rotulo="Montando o pedido…" />
        ) : !dados.tem_vendas ? (
          <p className="text-sm text-texto-2">
            {loja.nome} não vendeu nada na janela: não há o que abastecer.
          </p>
        ) : (
          <div className="flex flex-col">
            <div
              role="tablist"
              aria-label="Pedido por depósito"
              className="flex gap-0.5 overflow-x-auto border-b border-borda"
            >
              {abas.map((a) => {
                const ativa = a.valor === atual?.valor;
                return (
                  <button
                    key={a.valor}
                    type="button"
                    role="tab"
                    aria-selected={ativa}
                    aria-controls={ids.painel}
                    onClick={() => trocarOrigem(a.valor)}
                    className={`-mb-px flex shrink-0 flex-col items-start rounded-t-md border px-3 py-1.5 text-left text-xs ${
                      ativa
                        ? "border-borda border-b-superficie bg-superficie text-texto"
                        : "border-transparent bg-superficie-2/60 text-texto-mudo hover:text-texto"
                    }`}
                  >
                    <span className="font-semibold">{a.titulo}</span>
                    <span>
                      {formatarNumero(a.itens.length)} itens ·{" "}
                      {formatarNumero(porMarca(a.itens).length)} marcas
                    </span>
                  </button>
                );
              })}
            </div>
            <div
              id={ids.painel}
              role="tabpanel"
              aria-label={atual?.titulo}
              className="flex flex-col gap-3 pt-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <label
                  htmlFor={ids.marca}
                  className="text-xs font-medium text-texto-2"
                >
                  Marca
                </label>
                <select
                  id={ids.marca}
                  value={marca}
                  onChange={(ev) => setMarca(ev.target.value)}
                  className="campo w-56"
                >
                  <option value="">Todas</option>
                  {grupos.map(([m, itens]) => (
                    <option key={m} value={m}>
                      {m} ({formatarNumero(itens.length)})
                    </option>
                  ))}
                </select>
                {atual && (
                  <span className="ml-auto">
                    <BotaoExportar
                      caminho="/api/v1/estoque/pedido-abastecimento/exportar"
                      params={{
                        loja: loja.codigo,
                        deposito: atual.valor,
                        alvo_dias: alvo,
                        janela_dias: janelaDias,
                      }}
                      rotulo="Exportar pedido"
                    />
                  </span>
                )}
              </div>
              {visiveis.length === 0 ? (
                <EmptyState
                  icone={PackageCheck}
                  titulo="Nada a pedir deste depósito."
                />
              ) : (
                <div className="max-h-[70vh] overflow-auto rounded-md border border-borda">
                  <table className="w-full text-sm">
                    <caption className="sr-only">
                      Pedido de abastecimento de {loja.nome}: {atual?.titulo}
                    </caption>
                    <thead className="sticky top-0 z-10 bg-superficie-2 shadow-[inset_0_-1px_0_var(--color-borda)]">
                      <tr>
                        <th scope="col" className={TH}>
                          Produto
                        </th>
                        <th scope="col" className={TH}>
                          Situação
                        </th>
                        <th scope="col" className={`${TH} text-right`}>
                          Saldo loja
                        </th>
                        <th scope="col" className={`${TH} text-right`}>
                          Venda/dia
                        </th>
                        <th scope="col" className={`${TH} text-right`}>
                          Cobertura
                        </th>
                        <th scope="col" className={`${TH} text-right`}>
                          Falta
                        </th>
                        <th scope="col" className={`${TH} text-right`}>
                          Pedir
                        </th>
                        <th scope="col" className={`${TH} text-right`}>
                          No depósito
                        </th>
                      </tr>
                    </thead>
                    <tbody className="tabular">
                      {visiveis.map(([m, itens]) => (
                        <Fragment key={m}>
                          <tr className="bg-superficie-2/60">
                            <th
                              scope="colgroup"
                              colSpan={8}
                              className="px-3 py-1.5 text-left text-xs font-bold uppercase tracking-wide text-texto"
                            >
                              {m}{" "}
                              <span className="font-normal normal-case text-texto-mudo">
                                · {formatarNumero(itens.length)}{" "}
                                {itens.length === 1 ? "item" : "itens"}
                              </span>
                            </th>
                          </tr>
                          {itens.map((i) => (
                            <tr
                              key={`${i.id_produto}/${i.id_subproduto}`}
                              className="border-b border-borda/70 text-texto-2 hover:bg-superficie-2"
                            >
                              <td className="px-3 py-1.5">
                                <button
                                  type="button"
                                  onClick={() =>
                                    aoAbrirProduto({
                                      idProduto: i.id_produto,
                                      idSubproduto: i.id_subproduto,
                                    })
                                  }
                                  className="text-left hover:underline"
                                >
                                  <span className="font-semibold text-texto">
                                    {i.id_subproduto}
                                  </span>
                                  {i.descricao && (
                                    <span className="block text-xs text-texto-mudo">
                                      {i.descricao}
                                    </span>
                                  )}
                                </button>
                              </td>
                              <td className="px-3 py-1.5">
                                <SeloCobertura status={i.status_cobertura} />
                              </td>
                              <td className="px-3 py-1.5 text-right">
                                {formatarQuantidade(i.saldo_loja)}
                              </td>
                              <td className="px-3 py-1.5 text-right">
                                {formatarQuantidade(i.venda_media_diaria)}
                              </td>
                              <td className="whitespace-nowrap px-3 py-1.5 text-right">
                                {formatarCobertura(i.cobertura_dias)}
                              </td>
                              <td className="px-3 py-1.5 text-right">
                                {formatarQuantidade(i.necessidade)}
                              </td>
                              <td className="px-3 py-1.5 text-right font-semibold text-texto">
                                {formatarQuantidade(i.quantidade)}
                              </td>
                              <td className="px-3 py-1.5 text-right">
                                {formatarQuantidade(i.disponivel_deposito)}
                              </td>
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </details>
  );
}
