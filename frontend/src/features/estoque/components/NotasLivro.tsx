import { ChevronDown, ChevronRight, FileText, Siren, X } from "lucide-react";
import { Fragment, useState } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Pagination } from "../../../components/ui/Pagination";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { useValorEstavel } from "../../../hooks/useValorEstavel";
import { formatarDataHora, formatarMoeda, formatarNumero, rotuloDia } from "../../../lib/format";
import { getItensNotaLivro, getNotasLivro } from "../../../services/estoqueService";
import type { NotaLivro, ParamsLivro, ParamsNotasLivro } from "../../../types/api";
import { AvisoAfeta, SeloCategoria } from "./CategoriaMovimento";
import { CodigoProduto } from "./CodigoProduto";
import { Quantidade } from "./EstoqueTabela";

const TAMANHO_PAGINA = 25;
const TH = "px-3 py-2 font-semibold";
const TD = "px-3 py-2 align-top";

function Valor({ valor }: { valor: string | null }) {
  const negativo = valor !== null && valor.trim().startsWith("-");
  return <span className={negativo ? "text-critico-texto" : "text-texto"}>{formatarMoeda(valor)}</span>;
}

function NaoInformado() {
  return (
    <span className="text-texto-mudo" title="O ERP não informa">
      —
    </span>
  );
}

interface NotasLivroProps {

  params: ParamsLivro;

  coi: number | null;
  aoLimparCoi: () => void;
  rodada?: number;
}


export function NotasLivro({ params, coi, aoLimparCoi, rodada = 0 }: NotasLivroProps) {
  const [pagina, setPagina] = useState(1);
  const [aberta, setAberta] = useState<string | null>(null);
  const [soErradas, setSoErradas] = useState(false);
  const montados: ParamsNotasLivro = {
    ...params,
    ...(coi === null ? {} : { coi }),
    ...(soErradas ? { empresa_errada: true } : {}),
  };
  const filtros = useValorEstavel(montados);

  const [filtrosVistos, setFiltrosVistos] = useState(filtros);
  if (filtrosVistos !== filtros) {
    setFiltrosVistos(filtros);
    setPagina(1);
    setAberta(null);
  }
  const notas = useAsync((s) => getNotasLivro(filtros, pagina, TAMANHO_PAGINA, s), [filtros, pagina], rodada);
  const d = notas.data;

  return (
    <Panel
      titulo="Notas"
      subtitulo={
        "Cada documento com a data e a hora do lançamento e quem lançou. O ERP só informa quem lançou nas " +
        "notas de saída; entradas e saídas avulsas e balanços não têm cabeçalho no ERP, então aparecem só com o dia."
      }
      acao={
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            aria-pressed={soErradas}
            onClick={() => setSoErradas((v) => !v)}
            title="Notas de saída, fora as transferências, com o CNPJ de outra empresa do grupo como destinatário"
            className="btn btn-sm btn-secundario aria-pressed:border-critico aria-pressed:text-critico-texto"
          >
            <Siren aria-hidden className="size-4" />
            Emitidas na empresa errada
          </button>
          {coi !== null && (
            <button type="button" onClick={aoLimparCoi} className="btn btn-sm btn-fantasma">
              <X aria-hidden className="size-4" />
              COI {coi}: mostrar todos
            </button>
          )}
        </div>
      }
      nivel={2}
    >
      {notas.error ? (
        <ErrorState titulo="Falha ao carregar as notas" erro={notas.error} aoTentarNovamente={notas.recarregar} />
      ) : !d ? (
        <LoadingState rotulo="Carregando notas…" />
      ) : d.notas.length === 0 ? (
        <EmptyState
          icone={FileText}
          titulo={soErradas ? "Nenhuma nota emitida na empresa errada no período." : "Nenhuma nota com esses filtros."}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div
            aria-busy={notas.loading}
            className={`overflow-auto transition-opacity md:max-h-[70vh] md:rounded-lg md:border md:border-borda ${notas.loading ? "opacity-60" : ""}`}
          >
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Notas do livro de movimentação</caption>
              <thead className="md:sticky md:top-0">
                <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
                  <th scope="col" className={TH}>
                    <span className="sr-only">Produtos</span>
                  </th>
                  <th scope="col" className={TH}>Data e hora</th>
                  <th scope="col" className={TH}>Loja</th>
                  <th scope="col" className={TH}>Operação</th>
                  <th scope="col" className={TH}>Documento</th>
                  <th scope="col" className={TH}>Feito por</th>
                  <th scope="col" className={`${TH} text-right`}>Itens</th>
                  <th scope="col" className={`${TH} text-right`}>Valor</th>
                </tr>
              </thead>
              <tbody className="tabular">
                {d.notas.map((n) => {
                  const chave = `${n.empresa.id}/${n.id_planilha}`;
                  const expandida = aberta === chave;
                  return (
                    <Fragment key={chave}>
                      <LinhaNota nota={n} expandida={expandida} aoAlternar={() => setAberta(expandida ? null : chave)} />
                      {expandida && (
                        <tr className="bg-superficie-2/40">
                          <td colSpan={8} className="px-3 pb-3">
                            <ProdutosDaNota empresa={n.empresa.codigo} idPlanilha={n.id_planilha} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pagination
            pagina={d.pagina}
            totalPaginas={d.total_paginas}
            totalRegistros={d.total}
            tamanhoPagina={d.tamanho_pagina}
            itensNaPagina={d.notas.length}
            aoMudarPagina={setPagina}
            desabilitado={notas.loading}
          />
        </div>
      )}
    </Panel>
  );
}

function LinhaNota({ nota: n, expandida, aoAlternar }: { nota: NotaLivro; expandida: boolean; aoAlternar: () => void }) {
  const Icone = expandida ? ChevronDown : ChevronRight;
  return (
    <tr
      className={`border-t border-borda/60 ${n.empresa_errada ? "bg-critico/[0.06]" : n.afeta ? "" : "opacity-70"}`}
    >
      <td className={TD}>
        <button
          type="button"
          onClick={aoAlternar}
          aria-expanded={expandida}
          aria-label={`${expandida ? "Esconder" : "Ver"} produtos do documento ${n.id_planilha}`}
          className="btn btn-sm btn-fantasma px-1.5"
        >
          <Icone aria-hidden className="size-4" />
        </button>
      </td>
      <td className={`${TD} whitespace-nowrap`}>
        {n.momento ? formatarDataHora(n.momento) : (
          <>
            {rotuloDia(n.dia)} <span className="text-xs text-texto-mudo">· sem hora</span>
          </>
        )}
      </td>
      <td className={TD}>{n.empresa.codigo}</td>
      <td className={TD}>
        <SeloCategoria categoria={n.categoria} />
        <span className="block text-xs text-texto-2">
          {n.coi}
          {n.operacao && ` · ${n.operacao}`}
        </span>
        <AvisoAfeta afeta={n.afeta} />
      </td>
      <td className={`${TD} text-texto-2`}>
        {n.numero ? `Nota ${n.numero}` : n.id_planilha}
        {n.numero && <span className="block text-xs text-texto-mudo">{n.id_planilha}</span>}
        {n.destinatario && (
          <span className="block text-xs text-texto-mudo">
            Para: {n.destinatario}
            {n.destino_empresa && ` (empresa ${n.destino_empresa})`}
          </span>
        )}
        {n.empresa_errada && (
          <span
            className="mt-1 inline-flex items-center gap-1 rounded-full bg-critico/15 px-2 py-0.5 text-xs font-semibold text-critico-texto"
            title={`Quem fica com a mercadoria é a empresa ${n.destino_empresa}: a nota tem que ser cancelada e emitida lá.`}
          >
            <Siren aria-hidden className="size-3" />
            Empresa errada
          </span>
        )}
      </td>
      <td className={TD}>{n.usuario ?? <NaoInformado />}</td>
      <td className={`${TD} text-right`}>{formatarNumero(n.itens)}</td>
      <td className={`${TD} text-right`}>
        <Valor valor={n.valor} />
      </td>
    </tr>
  );
}

function ProdutosDaNota({ empresa, idPlanilha }: { empresa: string; idPlanilha: string }) {
  const itens = useAsync((s) => getItensNotaLivro(empresa, idPlanilha, s), [empresa, idPlanilha]);
  if (itens.error) {
    return <ErrorState titulo="Falha ao carregar os produtos" erro={itens.error} aoTentarNovamente={itens.recarregar} />;
  }
  if (!itens.data) return <LoadingState rotulo="Carregando produtos…" />;
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Produtos do documento {idPlanilha}</caption>
      <thead>
        <tr className="text-xs uppercase tracking-wide text-texto-mudo">
          <th scope="col" className={TH}>Seq.</th>
          <th scope="col" className={TH}>Produto</th>
          <th scope="col" className={`${TH} text-right`}>Quantidade</th>
          <th scope="col" className={`${TH} text-right`}>Valor</th>
        </tr>
      </thead>
      <tbody className="tabular">
        {itens.data.map((i, n) => (
          <tr key={`${i.sequencia ?? ""}/${i.id_subproduto}/${n}`} className="border-t border-borda/60">
            <td className="px-3 py-1.5 text-texto-mudo">{i.sequencia ?? "—"}</td>
            <td className="px-3 py-1.5">
              <CodigoProduto idProduto={i.id_produto} idSubproduto={i.id_subproduto} />
              {i.descricao && <span className="block text-xs text-texto-mudo">{i.descricao}</span>}
            </td>
            <td className="px-3 py-1.5 text-right">
              <Quantidade valor={i.quantidade} />
            </td>
            <td className="px-3 py-1.5 text-right">
              <Valor valor={i.valor} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
