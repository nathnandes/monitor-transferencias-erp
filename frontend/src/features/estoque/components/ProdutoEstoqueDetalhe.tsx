import { SearchX } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Modal } from "../../../components/ui/Modal";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { formatarCnpj, formatarDataHora, formatarMoeda, formatarQuantidade, rotuloDia } from "../../../lib/format";
import { ApiError } from "../../../services/apiClient";
import { getMovimentosEstoque, getProdutoEstoque } from "../../../services/estoqueService";
import type { EmpresaDoProduto, FornecedorDoProduto, ProdutoEstoque } from "../../../types/api";
import { formatarCobertura, SeloCobertura } from "./CoberturaEstoque";
import { Quantidade } from "./EstoqueTabela";
import { ExtratoProduto } from "./ExtratoProduto";
import { TabelaMovimentos } from "./MovimentosEstoque";

export interface ProdutoSelecionado {
  idProduto: string;
  idSubproduto: string;
}

interface ProdutoEstoqueDetalheProps {
  produto: ProdutoSelecionado | null;

  janelaDias?: number;
  aoFechar: () => void;
}


function rotuloProduto({ idProduto, idSubproduto }: ProdutoSelecionado): string {
  return idProduto === idSubproduto ? idProduto : `${idSubproduto} (grade ${idProduto})`;
}


export function ProdutoEstoqueDetalhe({ produto, janelaDias, aoFechar }: ProdutoEstoqueDetalheProps) {
  return (
    <Modal aberto={produto !== null} titulo={produto ? `Produto ${rotuloProduto(produto)}` : ""} aoFechar={aoFechar}>
      {produto && (
        <div className="flex flex-col gap-5">
          <Conteudo produto={produto} janelaDias={janelaDias} />
          <UltimosMovimentos produto={produto} />
        </div>
      )}
    </Modal>
  );
}

function Conteudo({ produto, janelaDias }: { produto: ProdutoSelecionado; janelaDias?: number }) {
  const { data, error, loading, recarregar } = useAsync(
    (s) => getProdutoEstoque(produto.idProduto, produto.idSubproduto, s, janelaDias),
    [produto.idProduto, produto.idSubproduto, janelaDias],
  );

  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState
        icone={SearchX}
        titulo="Produto sem estoque registrado"
        descricao="Nenhuma empresa tem linha de estoque ativa para este produto."
      />
    );
  }
  if (error) return <ErrorState erro={error} aoTentarNovamente={recarregar} />;
  if (loading || !data) return <LoadingState rotulo="Carregando estoque do produto…" />;
  return (
    <>
      <DetalheProduto produto={data} />
      <ExtratoProduto produto={produto} empresas={data.empresas.map((e) => e.empresa)} />
    </>
  );
}

function Total({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-borda bg-superficie-2/50 px-3 py-2">
      <dt className="text-xs text-texto-mudo">{rotulo}</dt>
      <dd className="tabular mt-0.5 text-lg">{children}</dd>
    </div>
  );
}

export function DetalheProduto({ produto }: { produto: ProdutoEstoque }) {
  return (
    <div className="flex flex-col gap-5">
      {(produto.descricao || produto.fabricante) && (
        <p className="-mb-2 font-medium text-texto">
          {produto.descricao && <span>{produto.descricao}</span>}
          {produto.fabricante && (
            <span className="block text-sm font-normal text-texto-2">Fabricante: {produto.fabricante}</span>
          )}
        </p>
      )}
      <section aria-label="Total das empresas">
        <dl className="grid grid-cols-3 gap-2">
          <Total rotulo="Saldo atual">
            <Quantidade valor={produto.saldo_atual} forte />
          </Total>
          <Total rotulo="Reservado">
            <Quantidade valor={produto.saldo_reservado} />
          </Total>
          <Total rotulo="Disponível">
            <Quantidade valor={produto.saldo_disponivel} forte />
          </Total>
        </dl>
        <CoberturaDoProduto produto={produto} />
        <p className="mt-2 text-xs text-texto-mudo">
          {produto.empresas_com_estoque} {produto.empresas_com_estoque === 1 ? "empresa" : "empresas"} com saldo
          {produto.atualizado_em && ` · consolidado em ${formatarDataHora(produto.atualizado_em)}`}
        </p>
      </section>

      <Fornecedores fornecedores={produto.fornecedores} />

      {produto.empresas.length === 0 ? (
        <p className="text-sm text-texto-2">Nenhuma empresa com linha de estoque ativa.</p>
      ) : (
        produto.empresas.map((e) => <BlocoEmpresa key={e.empresa.id} dados={e} />)
      )}
    </div>
  );
}




function Fornecedores({ fornecedores }: { fornecedores: FornecedorDoProduto[] }) {
  return (
    <section aria-label="Fornecedores" className="flex flex-col gap-2">
      <h3 className="font-semibold text-texto">Fornecedores</h3>
      {fornecedores.length === 0 ? (
        <p className="-mt-1 text-sm text-texto-2">Nenhuma compra deste item com o fornecedor identificado.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-borda">
          <table className="w-full text-sm">
            <caption className="sr-only">Fornecedores do produto, da compra mais recente</caption>
            <thead>
              <tr className="bg-superficie-2/50 text-xs uppercase tracking-wide text-texto-mudo">
                <th scope="col" className="px-3 py-1.5 text-left font-semibold">Fornecedor</th>
                <th scope="col" className="px-3 py-1.5 text-left font-semibold">Última compra</th>
                <th scope="col" className="px-3 py-1.5 text-right font-semibold">Custo últ.</th>
                <th scope="col" className="px-3 py-1.5 text-right font-semibold">Compras</th>
                <th scope="col" className="px-3 py-1.5 text-right font-semibold">Qtd.</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {fornecedores.map((f) => (
                <tr key={f.cnpj ?? f.nome} className="border-t border-borda/60">
                  <td className="px-3 py-1.5">
                    <span className="text-texto">{f.nome}</span>
                    {f.cnpj && <span className="block text-[11px] text-texto-mudo">{formatarCnpj(f.cnpj)}</span>}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5">
                    {rotuloDia(f.ultima_compra)}
                    <span className="block text-[11px] text-texto-mudo">empresa {f.ultima_empresa.codigo}</span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-right">{formatarMoeda(f.custo_ultima)}</td>
                  <td className="px-3 py-1.5 text-right">{f.compras}</td>
                  <td className="px-3 py-1.5 text-right"><Quantidade valor={f.quantidade} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BlocoEmpresa({ dados }: { dados: EmpresaDoProduto }) {
  const { empresa } = dados;
  return (
    <section aria-label={`Empresa ${empresa.codigo}`} className="rounded-lg border border-borda">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-borda bg-superficie-2/50 px-3 py-2">
        <h3 className="font-semibold text-texto">
          {empresa.codigo} · <span className="font-normal text-texto-2">{empresa.nome}</span>
        </h3>
        <span className="tabular text-sm">
          <Quantidade valor={dados.saldo_atual} forte />
          <span className="text-texto-mudo"> atual · </span>
          <Quantidade valor={dados.saldo_disponivel} />
          <span className="text-texto-mudo"> disp.</span>
        </span>
        {(dados.venda_media_diaria !== null || dados.status_cobertura) && (
          <span className="tabular flex w-full items-center gap-2 text-xs text-texto-2">
            <SeloCobertura status={dados.status_cobertura} />
            {dados.venda_media_diaria !== null && (
              <span>
                vende {formatarQuantidade(dados.venda_media_diaria)}/dia · cobre {formatarCobertura(dados.cobertura_dias)}
              </span>
            )}
          </span>
        )}
      </header>
      <PrecoDaEmpresa dados={dados} />
      <table className="w-full text-sm">
        <caption className="sr-only">Locais de estoque da empresa {empresa.codigo}</caption>
        <thead>
          <tr className="text-xs uppercase tracking-wide text-texto-mudo">
            <th scope="col" className="px-3 py-1.5 text-left font-semibold">Local</th>
            <th scope="col" className="px-3 py-1.5 text-right font-semibold">Atual</th>
            <th scope="col" className="px-3 py-1.5 text-right font-semibold">Reserv.</th>
            <th scope="col" className="px-3 py-1.5 text-right font-semibold">Disp.</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {dados.locais.map((local) => (
            <tr
              key={`${local.id_local_estoque}/${local.descricao_lote}`}
              className={`border-t border-borda/60 ${local.perda ? "opacity-60" : ""}`}
            >
              <td className="px-3 py-1.5">
                <span className="text-texto">{local.descricao_local_estoque ?? `Local ${local.id_local_estoque}`}</span>
                <span className="text-texto-mudo"> · {local.id_local_estoque}</span>
                {local.descricao_lote && <span className="text-texto-mudo"> · lote {local.descricao_lote}</span>}
                {local.perda && (
                  <StatusBadge tom="critico" className="ml-2">
                    Perda · {local.perda} (fora das somas)
                  </StatusBadge>
                )}
                {local.inativo_erp && (
                  <StatusBadge tom="neutro" className="ml-2">
                    Inativo no ERP
                  </StatusBadge>
                )}
                <span className="block text-[11px] text-texto-mudo">
                  Alterado no ERP em {formatarDataHora(local.data_alteracao_erp)}
                </span>
              </td>
              <td className="px-3 py-1.5 text-right"><Quantidade valor={local.saldo_atual} /></td>
              <td className="px-3 py-1.5 text-right"><Quantidade valor={local.saldo_reservado} /></td>
              <td className="px-3 py-1.5 text-right"><Quantidade valor={local.saldo_disponivel} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function CoberturaDoProduto({ produto }: { produto: ProdutoEstoque }) {
  if (!produto.janela) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-texto-2">
      <SeloCobertura status={produto.status_cobertura} />
      {produto.venda_media_diaria !== null ? (
        <span className="tabular">
          Vende {formatarQuantidade(produto.venda_media_diaria)}/dia na rede · disponível para{" "}
          <strong className="text-texto">{formatarCobertura(produto.cobertura_dias)}</strong>
        </span>
      ) : (
        <span>Sem venda nos últimos {produto.janela.dias} dias.</span>
      )}
    </div>
  );
}

function PrecoDaEmpresa({ dados }: { dados: EmpresaDoProduto }) {
  const { preco } = dados;
  if (!preco) {
    return (
      <p className="border-b border-borda/60 px-3 py-2 text-xs text-texto-mudo">
        Sem preço/custo sincronizado nesta empresa.
      </p>
    );
  }
  const emPromocao = Number(preco.preco_promocao_varejo ?? 0) > 0;
  const itens: [string, string][] = [
    ["Varejo", formatarMoeda(preco.preco_varejo)],
    ["Atacado", Number(preco.preco_atacado ?? 0) > 0 ? formatarMoeda(preco.preco_atacado) : "—"],
    ["Valor (custo)", formatarMoeda(dados.valor_custo)],
    ["Custo gerencial", formatarMoeda(preco.custo_gerencial)],
    ["Custo reposição", formatarMoeda(preco.custo_reposicao)],
    ["Custo nota fiscal", formatarMoeda(preco.custo_nota_fiscal)],
  ];
  return (
    <div className="border-b border-borda/60 px-3 py-2">
      <dl className="tabular grid grid-cols-3 gap-x-4 gap-y-1.5 text-sm">
        {itens.map(([rotulo, valor]) => (
          <div key={rotulo}>
            <dt className="text-[11px] text-texto-mudo">{rotulo}</dt>
            <dd className="text-texto">{valor}</dd>
          </div>
        ))}
      </dl>
      {emPromocao && (
        <p className="mt-1.5 text-xs text-texto-2">
          Promoção varejo: {formatarMoeda(preco.preco_promocao_varejo)}
          {preco.fim_promocao_varejo && ` até ${formatarDataHora(preco.fim_promocao_varejo)}`}
        </p>
      )}
    </div>
  );
}


export const ULTIMOS_MOVIMENTOS = 10;

function UltimosMovimentos({ produto }: { produto: ProdutoSelecionado }) {
  const { data, error, recarregar } = useAsync(
    (s) =>
      getMovimentosEstoque(
        { produto: produto.idProduto, subproduto: produto.idSubproduto },
        1,
        ULTIMOS_MOVIMENTOS,
        s,
      ),
    [produto.idProduto, produto.idSubproduto],
  );
  return (
    <section aria-label="Últimos movimentos" className="flex flex-col gap-2">
      <h3 className="font-semibold text-texto">Últimos movimentos</h3>
      <p className="-mt-1 text-xs text-texto-mudo">Entradas e saídas avulsas e balanços, do mais recente.</p>
      {error ? (
        <ErrorState titulo="Falha ao carregar os movimentos" erro={error} aoTentarNovamente={recarregar} />
      ) : !data ? (
        <LoadingState rotulo="Carregando movimentos do produto…" />
      ) : data.itens.length === 0 ? (
        <p className="text-sm text-texto-2">Nenhuma entrada/saída avulsa ou balanço registrado.</p>
      ) : (
        <>
          <TabelaMovimentos itens={data.itens} />
          {data.total > data.itens.length && (
            <p className="text-xs text-texto-mudo">
              {data.itens.length} de {data.total}. Veja todos na aba Movimentos, filtrando pelo produto.
            </p>
          )}
        </>
      )}
    </section>
  );
}
