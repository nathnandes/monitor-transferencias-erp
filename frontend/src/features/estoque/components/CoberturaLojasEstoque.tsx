import { EyeOff, PackageSearch, X } from "lucide-react";
import { useId, useState } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Pagination } from "../../../components/ui/Pagination";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { formatarNumero } from "../../../lib/format";
import {
  getCoberturaLojas,
  getEstoque,
  incluirExcecaoCobertura,
  removerExcecaoCobertura,
} from "../../../services/estoqueService";
import type {
  CoberturaEmpresa,
  ContagemCobertura,
  ItemEstoque,
  StatusCobertura,
} from "../../../types/api";
import {
  DICA_COBERTURA,
  JANELA_PADRAO,
  JANELAS_VENDAS,
  ROTULO_COBERTURA,
  STATUS_COBERTURA,
  SeloCobertura,
} from "./CoberturaEstoque";
import { EstoqueTabela } from "./EstoqueTabela";
import { ExcecoesCobertura } from "./ExcecoesCobertura";
import { PedidoAbastecimento } from "./PedidoAbastecimento";
import type { ProdutoSelecionado } from "./ProdutoEstoqueDetalhe";

const TAMANHO_PAGINA = 50;


interface Selecao {
  local: string;
  titulo: string;
  status: StatusCobertura;
}


interface Marcado {
  empresa: string;
  nomeEmpresa: string;
  idProduto: string;
  idSubproduto: string;
  desfeito: boolean;
}


interface LinhaGrade {
  local: string;
  titulo: string;
  detalhe: string;
  comSaldo: number | null;
  contagem: ContagemCobertura;
}

interface CoberturaLojasEstoqueProps {
  rodada: number;
  aoAbrirProduto: (produto: ProdutoSelecionado) => void;
}


function diaMes(iso: string): string {
  const [, mes, dia] = iso.split("-");
  return `${dia}/${mes}`;
}

function linhasDaEmpresa(e: CoberturaEmpresa): LinhaGrade[] {
  const locais = e.locais
    .filter((l) => l.produtos_com_saldo > 0)
    .map((l) => ({
      local: l.id_local,
      titulo: l.descricao ?? `Local ${l.id_local}`,
      detalhe:
        `local ${l.id_local}` +
        (l.somados.length > 0
          ? ` + ${l.somados.map((s) => s.descricao ?? `local ${s.id_local}`).join(" e ")}`
          : ""),
      comSaldo: l.produtos_com_saldo,
      contagem: l.produtos,
    }));
  return [
    {
      local: "",
      titulo: "Empresa inteira",
      detalhe: "soma dos locais",
      comSaldo: null,
      contagem: e.produtos,
    },
    ...locais,
  ];
}

const TH =
  "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-texto-mudo";


export function CoberturaLojasEstoque({
  rodada,
  aoAbrirProduto,
}: CoberturaLojasEstoqueProps) {
  const [janelaDias, setJanelaDias] = useState<number>(JANELA_PADRAO);
  const [empresa, setEmpresa] = useState("");
  const [selecao, setSelecao] = useState<Selecao | null>(null);
  const [pagina, setPagina] = useState(1);

  const [alteracoes, setAlteracoes] = useState(0);
  const [marcando, setMarcando] = useState<string | null>(null);
  const [marcado, setMarcado] = useState<Marcado | null>(null);
  const [erroMarcar, setErroMarcar] = useState<string | null>(null);
  const ids = { janela: useId(), painel: useId() };
  const janela = janelaDias !== JANELA_PADRAO ? janelaDias : undefined;

  const cobertura = useAsync(
    (s) => getCoberturaLojas(janela, s),
    [janela],
    rodada + alteracoes,
  );
  const dados = cobertura.data;

  const atual =
    dados?.empresas.find((e) => e.empresa.codigo === empresa) ??
    dados?.empresas[0];
  const codigoAtual = atual?.empresa.codigo;

  const lista = useAsync(
    (s) =>
      selecao && codigoAtual
        ? getEstoque(
            {
              empresa: codigoAtual,
              local: selecao.local || undefined,
              cobertura: selecao.status,
              ordenacao: "menor_cobertura",
              media: "baixa",
              so_locais_da_loja: true,
              janela_dias: janela,
            },
            pagina,
            TAMANHO_PAGINA,
            s,
          )
        : Promise.resolve(null),
    [selecao, pagina, janela, codigoAtual],
    rodada + alteracoes,
  );

  const mudou = () => setAlteracoes((n) => n + 1);

  const trocarLoja = (codigo: string) => {
    setEmpresa(codigo);
    setSelecao(null);
    setPagina(1);
    setMarcado(null);
    setErroMarcar(null);
  };

  const escolher = (linha: LinhaGrade, status: StatusCobertura) => {
    const mesma = selecao?.local === linha.local && selecao.status === status;
    setSelecao(
      mesma ? null : { local: linha.local, titulo: linha.titulo, status },
    );
    setPagina(1);
  };


  async function marcarExcecao(e: CoberturaEmpresa, item: ItemEstoque) {
    setMarcando(item.id_subproduto);
    setErroMarcar(null);
    try {
      await incluirExcecaoCobertura({
        empresa: e.empresa.codigo,
        codigo: item.id_subproduto,
        motivo: null,
      });
      setMarcado({
        empresa: e.empresa.codigo,
        nomeEmpresa: e.empresa.nome,
        idProduto: item.id_produto,
        idSubproduto: item.id_subproduto,
        desfeito: false,
      });
      mudou();
    } catch (err) {
      setErroMarcar(
        err instanceof Error
          ? err.message
          : "Não foi possível marcar a exceção.",
      );
    } finally {
      setMarcando(null);
    }
  }

  async function desfazer(m: Marcado) {
    setErroMarcar(null);
    try {
      await removerExcecaoCobertura(m.empresa, m.idProduto, m.idSubproduto);
      setMarcado({ ...m, desfeito: true });
      mudou();
    } catch (err) {
      setErroMarcar(
        err instanceof Error ? err.message : "Não foi possível desfazer.",
      );
    }
  }


  const grade = (e: CoberturaEmpresa) => {
    const semSaldo = e.locais.filter((l) => l.produtos_com_saldo === 0);
    return (
      <div className="overflow-x-auto rounded-md border border-borda">
        <table className="w-full text-sm">
          <caption className="sr-only">
            Cobertura de {e.empresa.nome} por local de estoque
          </caption>
          <thead className="bg-superficie-2 shadow-[inset_0_-1px_0_var(--color-borda)]">
            <tr>
              <th scope="col" className={TH}>
                Local de estoque
              </th>
              <th scope="col" className={`${TH} text-right`}>
                Com saldo
              </th>
              {STATUS_COBERTURA.map((s) => (
                <th
                  key={s}
                  scope="col"
                  title={DICA_COBERTURA[s]}
                  className={`${TH} text-right`}
                >
                  <SeloCobertura status={s} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="tabular">
            {linhasDaEmpresa(e).map((linha) => (
              <tr
                key={linha.local || "empresa"}
                className={`border-b border-borda/70 last:border-b-0 ${linha.local ? "" : "bg-superficie-2/50"}`}
              >
                <th scope="row" className="px-3 py-1.5 text-left font-normal">
                  <span
                    className={`block text-texto ${linha.local ? "" : "font-semibold"}`}
                  >
                    {linha.titulo}
                  </span>
                  <span className="block text-[11px] text-texto-mudo">
                    {linha.detalhe}
                  </span>
                </th>
                <td className="px-3 py-1.5 text-right text-texto-2">
                  {linha.comSaldo === null
                    ? "—"
                    : formatarNumero(linha.comSaldo)}
                </td>
                {STATUS_COBERTURA.map((s) => {
                  const n = linha.contagem[s];
                  const ativa =
                    selecao?.local === linha.local && selecao.status === s;
                  return (
                    <td key={s} className="p-0.5 text-right">
                      <button
                        type="button"
                        aria-pressed={ativa}
                        aria-label={`${ROTULO_COBERTURA[s]} em ${linha.titulo}: ${formatarNumero(n)}`}
                        onClick={() => escolher(linha, s)}
                        className={`w-full rounded px-2.5 py-1.5 text-right transition-colors ${
                          ativa
                            ? "bg-acento font-semibold text-superficie"
                            : n === 0
                              ? "text-texto-mudo hover:bg-superficie-2"
                              : "text-texto hover:bg-superficie-2 hover:underline"
                        } ${linha.local ? "" : "font-semibold"} ${cobertura.loading ? "opacity-60" : ""}`}
                      >
                        {formatarNumero(n)}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {e.desconsiderados.length > 0 && (
          <p className="border-t border-borda bg-superficie-2/40 px-3 py-1.5 text-[11px] text-texto-mudo">
            Desconsiderados (não são de venda):{" "}
            {e.desconsiderados
              .map((l) => l.descricao ?? `local ${l.id_local}`)
              .join(", ")}
            .
          </p>
        )}
        {semSaldo.length > 0 && (
          <p className="border-t border-borda bg-superficie-2/40 px-3 py-1.5 text-[11px] text-texto-mudo">
            Sem saldo positivo:{" "}
            {semSaldo
              .map((l) => l.descricao ?? `local ${l.id_local}`)
              .join(", ")}
            .
          </p>
        )}
      </div>
    );
  };


  const produtos = (e: CoberturaEmpresa, s: Selecao) => (
    <div className="flex flex-col rounded-md border border-borda">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-borda bg-superficie-2 px-3 py-2">
        <SeloCobertura status={s.status} />
        <span className="text-sm font-semibold text-texto">
          {ROTULO_COBERTURA[s.status]} em {s.titulo}
        </span>
        <span className="text-xs text-texto-mudo">
          {lista.data
            ? `${formatarNumero(lista.data.total)} produtos · menor cobertura e maior venda primeiro`
            : "carregando…"}
        </span>
        <button
          type="button"
          onClick={() => setSelecao(null)}
          aria-label="Fechar a lista de produtos"
          className="btn btn-sm btn-fantasma ml-auto"
        >
          <X aria-hidden className="size-4" />
        </button>
      </div>
      <div className="flex flex-col gap-3 p-3">
        <p className="text-[11px] text-texto-mudo">
          "Exceção" tira o produto da falta só nesta empresa (fica só no
          depósito, ou a loja não tem estrutura).
        </p>
        {marcado?.empresa === e.empresa.codigo && (
          <p role="status" className="text-xs text-texto-2">
            {marcado.desfeito
              ? `O produto ${marcado.idSubproduto} voltou a contar em ${marcado.nomeEmpresa}.`
              : `O produto ${marcado.idSubproduto} virou exceção em ${marcado.nomeEmpresa}.`}
            {!marcado.desfeito && (
              <button
                type="button"
                onClick={() => void desfazer(marcado)}
                className="ml-2 font-medium text-acento-texto underline"
              >
                Desfazer
              </button>
            )}
          </p>
        )}
        {erroMarcar && (
          <p role="alert" className="text-xs text-critico-texto">
            {erroMarcar}
          </p>
        )}
        {lista.error ? (
          <ErrorState
            titulo="Falha ao carregar os produtos"
            erro={lista.error}
            aoTentarNovamente={lista.recarregar}
          />
        ) : !lista.data ? (
          <LoadingState rotulo="Carregando produtos…" />
        ) : lista.data.itens.length === 0 ? (
          <EmptyState
            icone={PackageSearch}
            titulo="Nenhum produto nesta faixa."
          />
        ) : (
          <>
            <EstoqueTabela
              itens={lista.data.itens}
              porEmpresa
              janelaDias={lista.data.janela.dias}
              comCobertura={lista.data.tem_vendas}
              carregando={lista.loading}
              aoAbrir={(item) =>
                aoAbrirProduto({
                  idProduto: item.id_produto,
                  idSubproduto: item.id_subproduto,
                })
              }
              acaoExtra={(item) => (
                <button
                  type="button"
                  onClick={() => void marcarExcecao(e, item)}
                  disabled={marcando !== null}
                  className="btn btn-sm btn-fantasma max-md:w-full"
                  aria-label={`Marcar ${item.id_subproduto} como exceção de falta em ${e.empresa.codigo} - ${e.empresa.nome}`}
                  title="Não é falta nesta empresa: só fica no depósito, ou a loja não tem estrutura"
                >
                  <EyeOff aria-hidden className="size-4" />
                  <span>
                    {marcando === item.id_subproduto ? "Marcando…" : "Exceção"}
                  </span>
                </button>
              )}
            />
            <Pagination
              pagina={lista.data.pagina}
              totalPaginas={lista.data.total_paginas}
              totalRegistros={lista.data.total}
              tamanhoPagina={lista.data.tamanho_pagina}
              itensNaPagina={lista.data.itens.length}
              aoMudarPagina={setPagina}
              desabilitado={lista.loading}
            />
          </>
        )}
      </div>
    </div>
  );

  return (
    <Panel
      titulo="Cobertura por loja"
      subtitulo={
        (dados
          ? `Saldo de cada local ÷ o que a venda tirou do estoque da empresa por dia (menos devoluções), de ${diaMes(dados.janela.inicio)} a ${diaMes(dados.janela.fim)}.`
          : "Saldo de cada local ÷ o que a venda tirou do estoque da empresa por dia (menos devoluções).") +
        " O estoque não diz de que local saiu: locais que não vendem (trocas, avarias) mostram ruptura no que a loja vende." +
        " Clique num número para ver os produtos."
      }
      nivel={2}
      acao={
        <div className="flex items-center gap-2">
          <label
            htmlFor={ids.janela}
            className="text-xs font-medium text-texto-2"
          >
            Média de vendas
          </label>
          <select
            id={ids.janela}
            value={janelaDias}
            onChange={(ev) => {
              setJanelaDias(Number(ev.target.value));
              setPagina(1);
            }}
            className="campo w-40"
          >
            {JANELAS_VENDAS.map((d) => (
              <option key={d} value={d}>
                Últimos {d} dias
              </option>
            ))}
          </select>
        </div>
      }
    >
      {cobertura.error ? (
        <ErrorState
          titulo="Falha ao carregar a cobertura"
          erro={cobertura.error}
          aoTentarNovamente={cobertura.recarregar}
        />
      ) : !dados ? (
        <LoadingState rotulo="Carregando a cobertura das lojas…" />
      ) : !atual ? (
        <p className="text-sm text-texto-2">
          Nenhum estoque sincronizado ainda.
        </p>
      ) : (
        <div className="flex flex-col">
          <div
            role="tablist"
            aria-label="Lojas"
            className="flex gap-0.5 overflow-x-auto border-b border-borda"
          >
            {dados.empresas.map((e) => {
              const ativa = e.empresa.codigo === atual.empresa.codigo;
              return (
                <button
                  key={e.empresa.id}
                  type="button"
                  role="tab"
                  aria-selected={ativa}
                  aria-controls={ids.painel}
                  onClick={() => trocarLoja(e.empresa.codigo)}
                  className={`-mb-px flex shrink-0 flex-col items-start rounded-t-md border px-3 py-1.5 text-left text-xs ${
                    ativa
                      ? "border-borda border-b-superficie bg-superficie text-texto"
                      : "border-transparent bg-superficie-2/60 text-texto-mudo hover:text-texto"
                  }`}
                >
                  <span className="font-semibold">
                    {e.empresa.codigo} - {e.empresa.nome}
                  </span>
                  <span
                    className={
                      e.tem_vendas && e.produtos.ruptura > 0
                        ? "text-critico-texto"
                        : ""
                    }
                  >
                    {e.tem_vendas
                      ? `${formatarNumero(e.produtos.ruptura)} em ruptura`
                      : "depósito, sem venda"}
                  </span>
                </button>
              );
            })}
          </div>
          <div
            id={ids.painel}
            role="tabpanel"
            aria-label={`${atual.empresa.codigo} - ${atual.empresa.nome}`}
            className="flex flex-col gap-4 pt-4"
          >
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-texto-2">
              <h3 className="text-sm font-bold text-texto">
                {atual.empresa.codigo} - {atual.empresa.nome}
              </h3>
              <span>
                {formatarNumero(atual.locais.length)} locais de estoque
              </span>
              <span>{formatarNumero(atual.excecoes)} exceções de falta</span>
            </div>
            {!atual.tem_vendas ? (
              <p className="rounded-md border border-borda bg-superficie-2/40 px-3 py-2 text-sm text-texto-2">
                Esta empresa não vendeu nada nos últimos {dados.janela.dias}{" "}
                dias (depósito): não há ritmo de venda para calcular a cobertura
                dos {formatarNumero(atual.locais.length)} locais dela.
              </p>
            ) : (
              grade(atual)
            )}
            {selecao && atual.tem_vendas && produtos(atual, selecao)}
            {atual.tem_vendas && (
              <PedidoAbastecimento
                loja={atual.empresa}
                janelaDias={janela}
                recarga={rodada + alteracoes}
                aoAbrirProduto={aoAbrirProduto}
              />
            )}
            <ExcecoesCobertura
              empresa={atual.empresa}
              quantidade={atual.excecoes}
              recarga={alteracoes}
              aoMudar={mudou}
            />
          </div>
        </div>
      )}
    </Panel>
  );
}
