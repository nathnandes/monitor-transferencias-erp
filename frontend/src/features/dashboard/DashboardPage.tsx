import { Building2, ChartColumn, LayoutDashboard, Tv } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";

import { AppShell } from "../../components/layout/AppShell";
import { EnvironmentBadge } from "../../components/layout/EnvironmentBadge";
import { FiltroGlobalBar } from "../../components/layout/FiltroGlobalBar";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { Panel } from "../../components/ui/Panel";
import { IndicadorVariacao } from "../../components/ui/IndicadorVariacao";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { useAsync } from "../../hooks/useAsync";
import { useTemAba } from "../auth/AuthContext";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { formatarNumero } from "../../lib/format";
import { getHealthLive, getResumoDashboard } from "../../services/dashboardService";
import { getEmpresas } from "../../services/empresasService";
import { getIndicadoresEmpresas } from "../../services/indicadoresService";
import { ChartPanel } from "../../components/charts/ChartPanel";
import { SeverityChart } from "../../components/charts/SeverityChart";
import { StatusChart } from "../../components/charts/StatusChart";
import { CompanyStatusList } from "./components/CompanyStatusList";
import { IndicadoresEmpresas } from "./components/IndicadoresEmpresas";
import { MetricsGrid } from "./components/MetricsGrid";
import { ehDadoSimulado, ordenarSeveridades, statusDoResumo } from "../../lib/aggregations";
import { descreverEscopo, paramsDoResumo, variacaoDoFluxo } from "../../lib/resumoFiltrado";

export const TITULO_DASHBOARD = "Dashboard de Operações ERP";
export const SUBTITULO_DASHBOARD = "Monitoramento de transferências entre empresas · somente consulta";


export function DashboardPage() {
  const comTv = useTemAba("DASHBOARD.TV");
  const [rodada, setRodada] = useState(0);
  const filtroGlobal = useFiltroGlobal();
  const params = useValorEstavel(paramsDoResumo(filtroGlobal));

  const health = useAsync((s) => getHealthLive(s), []);
  const empresas = useAsync((s) => getEmpresas(s), [], rodada);
  const resumo = useAsync((s) => getResumoDashboard(params, s), [params], rodada);

  const paramsIndicadores = useValorEstavel({ empresa: params.empresa, data_inicial: params.data_inicial, data_final: params.data_final });
  const indicadores = useAsync((s) => getIndicadoresEmpresas(paramsIndicadores, s), [paramsIndicadores], rodada);
  const rotuloComparacao = filtroGlobal.comparacao?.rotulo;
  const escopo = descreverEscopo(filtroGlobal.descricaoPeriodo, resumo.data, filtroGlobal.filtro.empresa);
  const variacaoEventos = variacaoDoFluxo(resumo.data, "eventos", rotuloComparacao, "neutro");

  const atualizar = useCallback(() => setRodada((r) => r + 1), []);
  useAtualizacaoAutomatica(atualizar);

  const status = useMemo(() => (resumo.data ? statusDoResumo(resumo.data.transferencias) : []), [resumo.data]);
  const severidades = useMemo(
    () => (resumo.data ? ordenarSeveridades(resumo.data.eventos_por_severidade) : []),
    [resumo.data],
  );


  const simulado = (empresas.data ?? []).some((e) => ehDadoSimulado(e.id_erp));

  const atualizando = resumo.loading || empresas.loading || indicadores.loading;
  const carregandoResumo = resumo.loading && !resumo.data;
  const atualizandoResumo = resumo.loading && Boolean(resumo.data);

  const erroResumo = resumo.data ? null : resumo.error;

  const header = (
    <Header
      titulo={TITULO_DASHBOARD}
      subtitulo={SUBTITULO_DASHBOARD}
      selo={<EnvironmentBadge health={health.data} simulado={simulado} />}
      info={
        <IndicadorAtualizacao
          atualizadoEm={resumo.atualizadoEm}
          geradoEm={resumo.data?.gerado_em ?? null}
          atualizando={resumo.loading}
          fontes={["transferencias"]}
        />
      }
      aoAtualizar={atualizar}
      atualizando={atualizando}
      acoes={
        comTv && (
          <Link to={`/tv${filtroGlobal.query}`} className="btn btn-secundario shrink-0" title="Tela cheia para monitor, com atualização automática">
            <Tv aria-hidden className="size-4" />
            Modo TV
          </Link>
        )
      }
      filtros={
        <FiltroGlobalBar
          estado={filtroGlobal}
          empresas={empresas.data}
          carregandoEmpresas={empresas.loading && !empresas.data}
        />
      }
    />
  );

  return (
    <AppShell header={header}>
      <section id="indicadores" aria-labelledby="titulo-indicadores">
        <SectionHeader
          id="titulo-indicadores"
          titulo="Indicadores"
          descricao={
            rotuloComparacao
              ? `${escopo}. Setas comparam com ${rotuloComparacao}.`
              : `${escopo}. Escolha Hoje, Ontem, Mês ou Personalizado para comparar.`
          }
          icone={LayoutDashboard}
        />
        <MetricsGrid
          resumo={resumo.data}
          carregando={resumo.loading}
          erro={resumo.error}
          aoTentarNovamente={resumo.recarregar}
          rotuloComparacao={rotuloComparacao}
          escopo={escopo}
        />
      </section>

      <section
        id="indicadores-empresas"
        aria-labelledby="titulo-indicadores-empresas"
        className="-mx-2 rounded-painel bg-acento-suave/40 px-2 py-4 ring-1 ring-acento/30 sm:-mx-4 sm:px-4"
      >
        <SectionHeader
          id="titulo-indicadores-empresas"
          titulo="Indicadores por empresa"
          descricao={`${filtroGlobal.descricaoPeriodo} · uma coluna por ${
            { hora: "hora", dia: "dia", mes: "mês" }[indicadores.data?.granularidade ?? "dia"]
          }`}
          icone={Building2}
        />
        <IndicadoresEmpresas
          dados={indicadores.data}
          carregando={indicadores.loading}
          erro={indicadores.error}
          aoTentarNovamente={indicadores.recarregar}
          situacoes={resumo.data?.status_por_empresa}
        />
      </section>

      <section id="visao-geral" aria-labelledby="titulo-visao-geral">
        <SectionHeader
          id="titulo-visao-geral"
          titulo="Visão geral"
          descricao={escopo}
          icone={ChartColumn}
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartPanel
            titulo="Transferências por status"
            subtitulo="Criadas no período, pela situação de agora"
            carregando={carregandoResumo}
            atualizando={atualizandoResumo}
            erro={erroResumo}
            vazio={status.length === 0}
            mensagemVazio="Nenhuma transferência criada no período."
            aoTentarNovamente={resumo.recarregar}
            descricao={status.map((s) => `${s.status}: ${s.total}`).join(", ")}
          >
            <StatusChart dados={status} />
          </ChartPanel>
          <ChartPanel
            titulo="Eventos por severidade"
            subtitulo={
              <span className="flex flex-wrap items-baseline gap-x-2">
                Ocorridos no período
                {resumo.data?.periodo && <span>· {formatarNumero(resumo.data.periodo.eventos)} no total</span>}
                {variacaoEventos && <IndicadorVariacao variacao={variacaoEventos.valor} rotulo={variacaoEventos.rotulo} />}
              </span>
            }
            carregando={carregandoResumo}
            atualizando={atualizandoResumo}
            erro={erroResumo}
            vazio={severidades.every((s) => s.total === 0)}
            mensagemVazio="Nenhum evento no período."
            aoTentarNovamente={resumo.recarregar}
            descricao={severidades.map((s) => `${s.severidade}: ${s.total}`).join(", ")}
          >
            <SeverityChart dados={severidades} />
          </ChartPanel>
          {resumo.data && (
            <Panel
              titulo="Situação por empresa"
              subtitulo="Situação de agora, de qualquer data (não segue o período). Pendências e erros contam pela empresa de origem."
              className="lg:col-span-2"
            >
              <CompanyStatusList itens={resumo.data.status_por_empresa} limites={resumo.data.limites_pendencia} />
            </Panel>
          )}
        </div>
      </section>

    </AppShell>
  );
}
