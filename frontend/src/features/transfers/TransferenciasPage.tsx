import { ClipboardCheck, Info } from "lucide-react";
import { Link } from "react-router";
import { useCallback, useMemo, useState } from "react";

import { AppShell } from "../../components/layout/AppShell";
import { EnvironmentBadge } from "../../components/layout/EnvironmentBadge";
import { FiltroGlobalBar } from "../../components/layout/FiltroGlobalBar";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { BotaoExportar } from "../../components/ui/BotaoExportar";
import { ErrorState } from "../../components/ui/ErrorState";
import { useAsync } from "../../hooks/useAsync";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { opcoesDeStatus } from "../../lib/status";
import { getHealthLive } from "../../services/dashboardService";
import { getEmpresas } from "../../services/empresasService";
import { getTransferencias } from "../../services/transferenciasService";
import type { ParamsTransferencias } from "../../types/api";
import { useSessao, useTemAba } from "../auth/AuthContext";
import { ehDadoSimulado } from "../../lib/aggregations";
import { FilterBar } from "./components/FilterBar";
import { TransfersPanel } from "./components/TransfersPanel";
import { useTransferQuery } from "./hooks/useTransferQuery";
import { filtrosParaParams } from "./lib/queryFilters";

export const TITULO_TRANSFERENCIAS = "Transferências";
export const SUBTITULO_TRANSFERENCIAS = "Notas de transferência entre as lojas: quando saiu, quem emitiu e se já chegou";
export const AVISO_SEM_EMPRESAS =
  "A lista de empresas do filtro vem do módulo Dashboard, que não está liberado para o seu usuário.";


function montarParams(
  filtros: ParamsTransferencias,
  { filtro, intervalo }: Pick<ReturnType<typeof useFiltroGlobal>, "filtro" | "intervalo">,
): ParamsTransferencias {
  const params: ParamsTransferencias = { ...filtros };
  if (filtro.empresa) params.empresa = filtro.empresa;
  if (intervalo) {
    params.data_inicial = intervalo.inicio;
    params.data_final = intervalo.fim;
  }
  return params;
}


export function TransferenciasPage() {
  const comControle = useTemAba("TRANSFERENCIAS.CONTROLE");

  const {
    consulta,
    aplicarFiltros,
    limparFiltros,
    irParaPagina,
    mudarTamanhoPagina,
    abrirDetalhe,
    fecharDetalhe,
  } = useTransferQuery();
  const { filtros, pagina, tamanhoPagina } = consulta;
  const [rodada, setRodada] = useState(0);
  const filtroGlobal = useFiltroGlobal();


  const params = useValorEstavel(montarParams(filtrosParaParams(filtros), filtroGlobal));


  const { temModulo } = useSessao();
  const podeListarEmpresas = temModulo("DASHBOARD");

  const health = useAsync((s) => getHealthLive(s), []);
  const empresas = useAsync(
    (s) => (podeListarEmpresas ? getEmpresas(s) : Promise.resolve([])),
    [podeListarEmpresas],
    rodada,
  );
  const tabela = useAsync(
    (s) => getTransferencias(params, pagina, tamanhoPagina, s),
    [params, pagina, tamanhoPagina],
    rodada,
  );

  const atualizar = useCallback(() => setRodada((r) => r + 1), []);
  useAtualizacaoAutomatica(atualizar);

  const statusDisponiveis = useMemo(
    () => opcoesDeStatus((tabela.data?.itens ?? []).map((t) => t.status), filtros.status),
    [tabela.data, filtros.status],
  );


  const simulado =
    (empresas.data ?? []).some((e) => ehDadoSimulado(e.id_erp)) ||
    (tabela.data?.itens ?? []).some((t) => ehDadoSimulado(t.id_erp));

  const atualizando = tabela.loading || empresas.loading;
  const header = (
    <Header
      titulo={TITULO_TRANSFERENCIAS}
      subtitulo={SUBTITULO_TRANSFERENCIAS}
      selo={<EnvironmentBadge health={health.data} simulado={simulado} />}
      info={<IndicadorAtualizacao atualizadoEm={tabela.atualizadoEm} atualizando={tabela.loading} fontes={["transferencias"]} />}
      aoAtualizar={atualizar}
      atualizando={atualizando}
      acoes={
        <>
          <BotaoExportar caminho="/api/v1/transferencias/exportar" params={{ ...params }} />
          {comControle && (
            <Link to={`/transferencias/controle${filtroGlobal.query}`} className="btn btn-primario shrink-0">
              <ClipboardCheck aria-hidden className="size-4" />
              Controle
            </Link>
          )}
        </>
      }
      filtros={
        <FiltroGlobalBar
          estado={filtroGlobal}
          empresas={podeListarEmpresas ? empresas.data : null}
          carregandoEmpresas={empresas.loading && !empresas.data}
        />
      }
    />
  );

  return (
    <AppShell header={header}>
      <section id="consulta" aria-label="Consulta de transferências" className="flex flex-col gap-4">
        {empresas.error && (
          <ErrorState titulo="Falha ao carregar as empresas do filtro" erro={empresas.error} aoTentarNovamente={empresas.recarregar} />
        )}
        {!podeListarEmpresas && (
          <p className="flex items-start gap-2 rounded-lg border border-borda bg-superficie px-3 py-2.5 text-xs text-texto-2">
            <Info aria-hidden className="mt-px size-3.5 shrink-0 text-info-texto" />
            {AVISO_SEM_EMPRESAS}
          </p>
        )}
        <FilterBar
          empresas={empresas.data ?? []}
          carregandoEmpresas={empresas.loading && !empresas.data}
          opcoesStatus={statusDisponiveis}
          aplicados={filtros}
          aoAplicar={aplicarFiltros}
          aoLimpar={limparFiltros}
        />
        <TransfersPanel
          consulta={consulta}
          tabela={tabela}
          aoMudarPagina={irParaPagina}
          aoMudarTamanho={mudarTamanhoPagina}
          aoAbrirDetalhe={abrirDetalhe}
          aoFecharDetalhe={fecharDetalhe}
          aoLimparFiltros={limparFiltros}
        />
      </section>
    </AppShell>
  );
}
