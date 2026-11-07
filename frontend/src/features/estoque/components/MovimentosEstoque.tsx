import { ClipboardList, Eye, Search } from "lucide-react";
import { Fragment, useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Pagination } from "../../../components/ui/Pagination";
import { Panel } from "../../../components/ui/Panel";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { useTemAba } from "../../auth/AuthContext";
import { useValorEstavel } from "../../../hooks/useValorEstavel";
import { formatarDataHora, formatarMoeda, formatarNumero, rotuloDia } from "../../../lib/format";
import { hojeNoFuso } from "../../../lib/periodo";
import type { Tom } from "../../../lib/status";
import { getMovimentosEstoque } from "../../../services/estoqueService";
import type {
  EmpresaResumo,
  MovimentoEstoque,
  ParamsLivro,
  ParamsMovimentos,
  ResumoMovimentosDia,
  TipoMovimentoEstoque,
} from "../../../types/api";
import { CodigoProduto } from "./CodigoProduto";
import { Quantidade } from "./EstoqueTabela";
import { JustificativasAvulsas } from "./JustificativasAvulsas";
import type { ProdutoSelecionado } from "./ProdutoEstoqueDetalhe";

const TAMANHO_PAGINA = 50;

export const ROTULO_TIPO: Record<TipoMovimentoEstoque, string> = {
  entrada_avulsa: "Entrada avulsa",
  saida_avulsa: "Saída avulsa",
  balanco: "Balanço",
};
const TOM_TIPO: Record<TipoMovimentoEstoque, Tom> = {
  entrada_avulsa: "bom",
  saida_avulsa: "aviso",
  balanco: "info",
};

type TipoAvulsa = "entrada_avulsa" | "saida_avulsa";
const TIPOS_AVULSA: TipoAvulsa[] = ["entrada_avulsa", "saida_avulsa"];

export function SeloTipo({ tipo }: { tipo: TipoMovimentoEstoque }) {
  return <StatusBadge tom={TOM_TIPO[tipo]}>{ROTULO_TIPO[tipo]}</StatusBadge>;
}


function Valor({ valor }: { valor: string | null }) {
  const negativo = valor !== null && valor.trim().startsWith("-");
  return <span className={negativo ? "text-critico-texto" : "text-texto-2"}>{formatarMoeda(valor)}</span>;
}

interface MovimentosEstoqueProps {

  empresas: EmpresaResumo[];

  rodada?: number;
  aoAbrirProduto: (produto: ProdutoSelecionado) => void;
}


export function MovimentosEstoque({ empresas, rodada = 0, aoAbrirProduto }: MovimentosEstoqueProps) {
  const comJustificativas = useTemAba("ESTOQUE.JUSTIFICATIVAS");
  const hoje = hojeNoFuso();

  const [inicio, setInicio] = useState(hoje);
  const [fim, setFim] = useState(hoje);
  const [empresa, setEmpresa] = useState("");
  const [tipo, setTipo] = useState<TipoAvulsa | "">("");
  const [produtoDigitado, setProdutoDigitado] = useState("");
  const [produto, setProduto] = useState("");
  const [pagina, setPagina] = useState(1);
  const ids = { inicio: useId(), fim: useId(), empresa: useId(), tipo: useId(), produto: useId() };

  const periodoValido = Boolean(inicio && fim && inicio <= fim);
  const montados: ParamsMovimentos = {};
  if (periodoValido) {
    montados.data_inicial = inicio;
    montados.data_final = fim;
  }
  if (empresa) montados.empresa = empresa;

  montados.tipo = tipo || "avulsas";
  if (produto) montados.produto = produto;
  const filtros = useValorEstavel(montados);

  const doPeriodo: ParamsLivro = {};
  if (periodoValido) {
    doPeriodo.data_inicial = inicio;
    doPeriodo.data_final = fim;
  }
  if (empresa) doPeriodo.empresa = empresa;

  const movimentos = useAsync(
    (s) => getMovimentosEstoque(filtros, pagina, TAMANHO_PAGINA, s),
    [filtros, pagina],
    rodada,
  );

  const filtrar = <T,>(definir: (valor: T) => void) => (valor: T) => {
    definir(valor);
    setPagina(1);
  };
  const buscarProduto = (evento: FormEvent) => {
    evento.preventDefault();
    filtrar(setProduto)(produtoDigitado.trim());
  };
  const d = movimentos.data;
  const cobertura = d?.cobertura;

  return (
    <div className="flex flex-col gap-4">
      <Panel
        titulo="Entradas e saídas avulsas"
        subtitulo={
          "Lançamentos avulsos de estoque (COI 80 e 8080) lidos do ERP. Quantidade e valor com o efeito no " +
          "estoque: entrada positiva, saída negativa. Os balanços estão na aba Balanço." +
          (cobertura?.desde && cobertura.ate
            ? ` Dias lidos: ${rotuloDia(cobertura.desde)} a ${rotuloDia(cobertura.ate)}.`
            : "") +
          (cobertura?.atualizado_em ? ` Atualizado em ${formatarDataHora(cobertura.atualizado_em)}.` : "")
        }
        nivel={2}
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex w-40 flex-col gap-1.5">
            <label htmlFor={ids.inicio} className="text-xs font-medium text-texto-2">
              De
            </label>
            <input
              id={ids.inicio}
              type="date"
              value={inicio}
              max={fim || undefined}
              onChange={(e) => filtrar(setInicio)(e.target.value)}
              className="campo"
            />
          </div>
          <div className="flex w-40 flex-col gap-1.5">
            <label htmlFor={ids.fim} className="text-xs font-medium text-texto-2">
              Até
            </label>
            <input
              id={ids.fim}
              type="date"
              value={fim}
              min={inicio || undefined}
              onChange={(e) => filtrar(setFim)(e.target.value)}
              className="campo"
            />
          </div>
          <div className="flex w-56 flex-col gap-1.5">
            <label htmlFor={ids.empresa} className="text-xs font-medium text-texto-2">
              Empresa
            </label>
            <select
              id={ids.empresa}
              value={empresa}
              onChange={(e) => filtrar(setEmpresa)(e.target.value)}
              className="campo"
            >
              <option value="">Todas</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.codigo}>
                  {e.codigo} - {e.nome}
                </option>
              ))}
            </select>
          </div>
          <div className="flex w-44 flex-col gap-1.5">
            <label htmlFor={ids.tipo} className="text-xs font-medium text-texto-2">
              Tipo
            </label>
            <select
              id={ids.tipo}
              value={tipo}
              onChange={(e) => filtrar(setTipo)(e.target.value as TipoAvulsa | "")}
              className="campo"
            >
              <option value="">Todos</option>
              {TIPOS_AVULSA.map((t) => (
                <option key={t} value={t}>
                  {ROTULO_TIPO[t]}
                </option>
              ))}
            </select>
          </div>
          <form role="search" aria-label="Buscar produto nos movimentos" onSubmit={buscarProduto} className="flex items-end gap-2">
            <div className="flex w-40 flex-col gap-1.5">
              <label htmlFor={ids.produto} className="text-xs font-medium text-texto-2">
                Produto
              </label>
              <input
                id={ids.produto}
                type="search"
                inputMode="numeric"
                value={produtoDigitado}
                onChange={(e) => {
                  setProdutoDigitado(e.target.value);
                  if (!e.target.value) filtrar(setProduto)("");
                }}
                placeholder="Ex.: 9798"
                className="campo"
              />
            </div>
            <button type="submit" className="btn btn-sm btn-secundario">
              <Search aria-hidden className="size-4" />
              Buscar
            </button>
          </form>
        </div>
        {!periodoValido && (
          <p className="mt-2 text-xs text-aviso-texto">Período incompleto: mostrando todos os dias já lidos.</p>
        )}
      </Panel>

      {comJustificativas && (
        <JustificativasAvulsas params={doPeriodo} tipo={tipo || undefined} rodada={rodada} aoAbrirProduto={aoAbrirProduto} />
      )}

      {movimentos.error ? (
        <ErrorState
          titulo="Falha ao carregar os movimentos"
          erro={movimentos.error}
          aoTentarNovamente={movimentos.recarregar}
        />
      ) : !d ? (
        <LoadingState rotulo="Carregando movimentos…" />
      ) : (
        <>
          <Panel titulo="Resumo por dia" subtitulo="Por empresa, dia e tipo, com os filtros acima." nivel={2}>
            {d.resumo.length === 0 ? (
              <p className="text-sm text-texto-2">Nada no período.</p>
            ) : (
              <ResumoPorDia resumo={d.resumo} />
            )}
          </Panel>

          <Panel titulo="Itens" subtitulo="Do mais recente para o mais antigo." nivel={2}>
            {d.itens.length === 0 ? (
              <EmptyState
                icone={ClipboardList}
                titulo="Nenhum movimento com esses filtros."
                descricao={
                  cobertura?.desde ? undefined : "Os movimentos aparecem aqui depois da primeira sincronização."
                }
              />
            ) : (
              <div className="flex flex-col gap-4">
                <TabelaMovimentos itens={d.itens} carregando={movimentos.loading} aoAbrirProduto={aoAbrirProduto} />
                <Pagination
                  pagina={d.pagina}
                  totalPaginas={d.total_paginas}
                  totalRegistros={d.total}
                  tamanhoPagina={d.tamanho_pagina}
                  itensNaPagina={d.itens.length}
                  aoMudarPagina={setPagina}
                  desabilitado={movimentos.loading}
                />
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

const TH = "px-3 py-2 font-semibold";
const TD = "px-3 py-2";

const chaveEvento = (b: ResumoMovimentosDia) => `${b.dia}/${b.empresa.id}`;

interface EventosBalancoProps {
  eventos: ResumoMovimentosDia[];

  aberto: ResumoMovimentosDia | null;
  aoAlternar: (r: ResumoMovimentosDia | null) => void;

  detalhe: ReactNode;
}

export function EventosBalanco({ eventos, aberto, aoAlternar, detalhe }: EventosBalancoProps) {
  const chaveAberta = aberto ? chaveEvento(aberto) : null;
  const refDetalhe = useRef<HTMLLIElement>(null);
  useEffect(() => {
    if (chaveAberta) refDetalhe.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, [chaveAberta]);
  return (


    <ul aria-label="Eventos de balanço" className="grid grid-flow-dense gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {eventos.map((b) => {
        const chave = chaveEvento(b);
        const estaAberto = chave === chaveAberta;
        const idDetalhe = `itens-balanco-${chave.replace("/", "-")}`;
        return (
          <Fragment key={chave}>
            <li
              aria-label={`Balanço ${rotuloDia(b.dia)} loja ${b.empresa.codigo}`}
              className={`flex flex-col gap-2 rounded-lg border px-3 py-2.5 ${
                estaAberto ? "border-acento bg-superficie-2" : "border-borda bg-superficie-2/40"
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-semibold text-texto">
                  {rotuloDia(b.dia)} · {b.empresa.codigo} <span className="font-normal text-texto-2">{b.empresa.nome}</span>
                </span>
                <span className="text-xs text-texto-mudo">{formatarNumero(b.itens)} itens</span>
              </div>
              <dl className="tabular grid grid-cols-3 gap-2 text-sm">
                <div>
                  <dt className="text-[11px] text-texto-mudo">Falta ({formatarNumero(b.falta_itens ?? 0)})</dt>
                  <dd>
                    <Valor valor={b.falta_valor} />
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] text-texto-mudo">Sobra ({formatarNumero(b.sobra_itens ?? 0)})</dt>
                  <dd>
                    <Valor valor={b.sobra_valor} />
                  </dd>
                </div>
                <div>
                  <dt className="text-[11px] text-texto-mudo">Líquido</dt>
                  <dd className="font-semibold">
                    <Valor valor={b.valor} />
                  </dd>
                </div>
              </dl>
              <button
                type="button"
                onClick={() => aoAlternar(estaAberto ? null : b)}
                aria-expanded={estaAberto}
                aria-controls={estaAberto ? idDetalhe : undefined}
                className="btn btn-sm btn-fantasma self-start"
              >
                {estaAberto ? "Fechar itens" : "Ver itens"}
              </button>
            </li>
            {estaAberto && (
              <li
                ref={refDetalhe}
                id={idDetalhe}
                aria-label={`Itens do balanço ${rotuloDia(b.dia)} loja ${b.empresa.codigo}`}
                className="col-span-full scroll-mt-4 rounded-lg border border-acento/60 bg-superficie p-3"
              >
                {detalhe}
              </li>
            )}
          </Fragment>
        );
      })}
    </ul>
  );
}

function ResumoPorDia({ resumo }: { resumo: ResumoMovimentosDia[] }) {
  return (
    <div className="overflow-auto md:max-h-[50vh] md:rounded-lg md:border md:border-borda">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Resumo dos movimentos por empresa, dia e tipo</caption>
        <thead className="md:sticky md:top-0">
          <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
            <th scope="col" className={TH}>Dia</th>
            <th scope="col" className={TH}>Empresa</th>
            <th scope="col" className={TH}>Tipo</th>
            <th scope="col" className={`${TH} text-right`}>Itens</th>
            <th scope="col" className={`${TH} text-right`}>Quantidade</th>
            <th scope="col" className={`${TH} text-right`}>Valor</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {resumo.map((r) => (
            <tr key={`${r.dia}/${r.empresa.id}/${r.tipo}`} className="border-t border-borda/60">
              <td className={TD}>{rotuloDia(r.dia)}</td>
              <td className={TD}>
                {r.empresa.codigo} <span className="text-texto-mudo">{r.empresa.nome}</span>
              </td>
              <td className={TD}>
                <SeloTipo tipo={r.tipo} />
              </td>
              <td className={`${TD} text-right`}>{formatarNumero(r.itens)}</td>
              <td className={`${TD} text-right`}>
                <Quantidade valor={r.quantidade} />
              </td>
              <td className={`${TD} text-right`}>
                <Valor valor={r.valor} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface TabelaMovimentosProps {
  itens: MovimentoEstoque[];
  carregando?: boolean;

  aoAbrirProduto?: (produto: ProdutoSelecionado) => void;
}

export function TabelaMovimentos({ itens, carregando = false, aoAbrirProduto }: TabelaMovimentosProps) {
  return (
    <div
      aria-busy={carregando}
      className={`overflow-auto transition-opacity md:max-h-[70vh] md:rounded-lg md:border md:border-borda ${carregando ? "opacity-60" : ""}`}
    >
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Movimentos de estoque</caption>
        <thead className="md:sticky md:top-0">
          <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
            <th scope="col" className={TH}>Dia</th>
            <th scope="col" className={TH}>Empresa</th>
            <th scope="col" className={TH}>Tipo</th>
            <th scope="col" className={TH}>Documento</th>
            {aoAbrirProduto && <th scope="col" className={TH}>Produto</th>}
            <th scope="col" className={`${TH} text-right`}>Quantidade</th>
            <th scope="col" className={`${TH} text-right`}>Valor</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {itens.map((m) => {
            const subproduto = m.id_subproduto ?? m.id_produto;
            return (
              <tr key={m.id} className="border-t border-borda/60">
                <td className={TD}>{rotuloDia(m.dia)}</td>
                <td className={TD}>{m.empresa.codigo}</td>
                <td className={TD}>
                  <SeloTipo tipo={m.tipo} />
                </td>
                <td className={`${TD} text-texto-2`}>
                  {m.id_planilha}
                  {m.sequencia && <span className="text-texto-mudo"> · {m.sequencia}</span>}
                </td>
                {aoAbrirProduto && (
                  <td className={TD}>
                    <button
                      type="button"
                      onClick={() => aoAbrirProduto({ idProduto: m.id_produto, idSubproduto: subproduto })}
                      aria-label={`Ver estoque do produto ${subproduto}`}
                      className="inline-flex items-center gap-1.5 text-left font-medium text-texto hover:underline"
                    >
                      <Eye aria-hidden className="size-3.5 shrink-0 text-texto-mudo" />
                      <span>
                        <CodigoProduto idProduto={m.id_produto} idSubproduto={subproduto} />
                      </span>
                    </button>
                    {m.descricao && <span className="block text-xs text-texto-mudo">{m.descricao}</span>}
                  </td>
                )}
                <td className={`${TD} text-right`}>
                  <Quantidade valor={m.quantidade} />
                </td>
                <td className={`${TD} text-right`}>
                  <Valor valor={m.valor} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
