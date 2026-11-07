import { FunnelX, LoaderCircle, SearchX } from "lucide-react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Pagination } from "../../../components/ui/Pagination";
import { Panel } from "../../../components/ui/Panel";
import type { EstadoAsync } from "../../../hooks/useAsync";
import type { PaginaTransferencias } from "../../../types/api";
import { TAMANHOS_PAGINA, temFiltro, type ConsultaTransferencias } from "../lib/queryFilters";
import { TransferDetails } from "./TransferDetails";
import { TransfersTable } from "./TransfersTable";

interface TransfersPanelProps {
  consulta: ConsultaTransferencias;
  tabela: EstadoAsync<PaginaTransferencias>;
  aoMudarPagina: (pagina: number) => void;
  aoMudarTamanho: (tamanho: number) => void;
  aoAbrirDetalhe: (id: number) => void;
  aoFecharDetalhe: () => void;
  aoLimparFiltros: () => void;
}


export function TransfersPanel({
  consulta,
  tabela,
  aoMudarPagina,
  aoMudarTamanho,
  aoAbrirDetalhe,
  aoFecharDetalhe,
  aoLimparFiltros,
}: TransfersPanelProps) {
  const { data, error, loading, recarregar } = tabela;

  let corpo;
  if (error) {
    corpo = <ErrorState titulo="Não foi possível carregar as transferências" erro={error} aoTentarNovamente={recarregar} />;
  } else if (!data) {
    corpo = <LoadingState rotulo="Carregando transferências..." />;
  } else if (data.total === 0) {
    corpo = (
      <EmptyState
        icone={SearchX}
        titulo="Nenhuma transferência encontrada"
        descricao={temFiltro(consulta.filtros) ? "Nenhum registro atende aos filtros aplicados." : "Não há transferências registradas."}
        acao={
          temFiltro(consulta.filtros) && (
            <button type="button" onClick={aoLimparFiltros} className="btn btn-sm btn-acento-suave">
              <FunnelX aria-hidden className="size-3.5" />
              Limpar filtros
            </button>
          )
        }
      />
    );
  } else if (data.itens.length === 0) {

    corpo = (
      <EmptyState
        titulo={`A página ${data.pagina} não existe`}
        descricao={`A consulta tem ${data.total_paginas} ${data.total_paginas === 1 ? "página" : "páginas"}.`}
        acao={
          <button type="button" onClick={() => aoMudarPagina(data.total_paginas)} className="btn btn-sm btn-secundario">
            Ir para a última página
          </button>
        }
      />
    );
  } else {
    corpo = (
      <div className="flex flex-col gap-3">
        <TransfersTable itens={data.itens} carregando={loading} aoAbrir={aoAbrirDetalhe} />
        <Pagination
          pagina={data.pagina}
          totalPaginas={data.total_paginas}
          totalRegistros={data.total}
          tamanhoPagina={data.tamanho_pagina}
          itensNaPagina={data.itens.length}
          aoMudarPagina={aoMudarPagina}
          opcoesTamanho={TAMANHOS_PAGINA}
          aoMudarTamanho={aoMudarTamanho}
          desabilitado={loading}
        />
      </div>
    );
  }

  return (
    <Panel
      id="transferencias"
      titulo="Transferências"
      subtitulo="Mais recentes primeiro. Datas no fuso local. Somente consulta."
      acao={
        loading &&
        data && (
          <span role="status" className="inline-flex items-center gap-1.5 text-xs text-texto-mudo">
            <LoaderCircle aria-hidden className="size-3.5 animate-spin text-acento-forte" />
            Atualizando
          </span>
        )
      }
    >
      {corpo}
      <TransferDetails id={consulta.detalheId} aoFechar={aoFecharDetalhe} />
    </Panel>
  );
}
