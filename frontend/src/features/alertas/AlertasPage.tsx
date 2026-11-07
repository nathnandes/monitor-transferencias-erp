import { BellRing, CircleCheck, CircleX, Info, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";

import { AppShell } from "../../components/layout/AppShell";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { MetricCard } from "../../components/ui/MetricCard";
import { Pagination } from "../../components/ui/Pagination";
import { Panel } from "../../components/ui/Panel";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { formatarDataHora, formatarNumero, tempoRelativo } from "../../lib/format";
import { tomDaSeveridade } from "../../lib/status";
import { getAlertas, getResumoAlertas } from "../../services/alertasService";
import type { Alerta, ParamsAlertas, Severidade, StatusAlerta } from "../../types/api";

export const TITULO_ALERTAS = "Alertas";
const SUBTITULO = "Situações que precisam de atenção, abertas pelo monitoramento · somente consulta";


const INTERVALO_ATUALIZACAO_MS = 60_000;

const ROTULO_SEVERIDADE: Record<Severidade, string> = {
  CRITICAL: "Crítico",
  ERROR: "Erro",
  WARNING: "Atenção",
  INFO: "Informativo",
};
const ORDEM_SEVERIDADE: Severidade[] = ["CRITICAL", "ERROR", "WARNING", "INFO"];
const ICONE_SEVERIDADE: Record<Severidade, LucideIcon> = {
  CRITICAL: OctagonAlert,
  ERROR: CircleX,
  WARNING: TriangleAlert,
  INFO: Info,
};

type FiltroStatus = StatusAlerta | "";

function SeveridadeBadge({ severidade }: { severidade: Severidade }) {
  return <StatusBadge tom={tomDaSeveridade(severidade)}>{ROTULO_SEVERIDADE[severidade]}</StatusBadge>;
}

function LinhaAlerta({ alerta }: { alerta: Alerta }) {
  return (
    <li className="flex flex-col gap-2 border-b border-borda/70 py-3 last:border-b-0 sm:flex-row sm:items-start sm:gap-4">
      <div className="flex shrink-0 items-center gap-2 sm:w-28 sm:flex-col sm:items-start">
        <SeveridadeBadge severidade={alerta.severidade} />
        {alerta.status === "RESOLVIDO" && <StatusBadge tom="bom">Resolvido</StatusBadge>}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-texto">{alerta.titulo}</p>
        <p className="mt-1 whitespace-pre-line text-xs text-texto-2">{alerta.mensagem}</p>
      </div>
      <div className="shrink-0 text-xs text-texto-mudo sm:w-44 sm:text-right">
        <p>
          Aberto <time dateTime={alerta.aberto_em}>{tempoRelativo(alerta.aberto_em)}</time>
        </p>
        <p>{formatarDataHora(alerta.aberto_em)}</p>
        {alerta.resolvido_em && <p className="text-bom-texto">Resolvido {formatarDataHora(alerta.resolvido_em)}</p>}
      </div>
    </li>
  );
}


export function AlertasPage() {
  const [status, setStatus] = useState<FiltroStatus>("ABERTO");
  const [severidade, setSeveridade] = useState<Severidade | "">("");
  const [pagina, setPagina] = useState(1);
  const [rodada, setRodada] = useState(0);
  const idStatus = useId();
  const idSeveridade = useId();

  const atualizar = useCallback(() => setRodada((r) => r + 1), []);


  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") atualizar();
    }, INTERVALO_ATUALIZACAO_MS);
    return () => window.clearInterval(id);
  }, [atualizar]);

  const montados: ParamsAlertas = {};
  if (status) montados.status = status;
  if (severidade) montados.severidade = severidade;
  const filtros = useValorEstavel(montados);

  const resumo = useAsync((s) => getResumoAlertas(s), [], rodada);
  const lista = useAsync((s) => getAlertas(filtros, pagina, 20, s), [filtros, pagina], rodada);

  const mudarStatus = (valor: FiltroStatus) => {
    setStatus(valor);
    setPagina(1);
  };
  const mudarSeveridade = (valor: Severidade | "") => {
    setSeveridade(valor);
    setPagina(1);
  };

  const header = (
    <Header
      titulo={TITULO_ALERTAS}
      subtitulo={SUBTITULO}
      info={<IndicadorAtualizacao atualizadoEm={lista.atualizadoEm} atualizando={lista.loading} />}
      aoAtualizar={atualizar}
      atualizando={lista.loading || resumo.loading}
    />
  );

  const porSeveridade = resumo.data?.por_severidade;

  return (
    <AppShell header={header}>
      <section aria-label="Alertas abertos por severidade" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <MetricCard
          rotulo="Abertos"
          valor={resumo.data ? formatarNumero(resumo.data.abertos) : undefined}
          icone={BellRing}
          destaque
          carregando={resumo.loading && !resumo.data}
        />
        {ORDEM_SEVERIDADE.map((s) => (
          <MetricCard
            key={s}
            rotulo={ROTULO_SEVERIDADE[s]}
            icone={ICONE_SEVERIDADE[s]}
            valor={porSeveridade ? formatarNumero(porSeveridade[s]) : undefined}
            tom={porSeveridade?.[s] ? tomDaSeveridade(s) : "neutro"}
            carregando={resumo.loading && !resumo.data}
          />
        ))}
      </section>
      {resumo.error && (
        <ErrorState titulo="Falha ao carregar o resumo" erro={resumo.error} aoTentarNovamente={resumo.recarregar} />
      )}

      <Panel
        titulo="Lista de alertas"
        subtitulo="Abertos primeiro; dentro de cada grupo, o mais recente primeiro."
        nivel={2}
        acao={
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex w-36 flex-col gap-1.5">
              <label htmlFor={idStatus} className="text-xs font-medium text-texto-2">
                Situação
              </label>
              <select
                id={idStatus}
                value={status}
                onChange={(e) => mudarStatus(e.target.value as FiltroStatus)}
                className="campo"
              >
                <option value="ABERTO">Abertos</option>
                <option value="RESOLVIDO">Resolvidos</option>
                <option value="">Todos</option>
              </select>
            </div>
            <div className="flex w-36 flex-col gap-1.5">
              <label htmlFor={idSeveridade} className="text-xs font-medium text-texto-2">
                Severidade
              </label>
              <select
                id={idSeveridade}
                value={severidade}
                onChange={(e) => mudarSeveridade(e.target.value as Severidade | "")}
                className="campo"
              >
                <option value="">Todas</option>
                {ORDEM_SEVERIDADE.map((s) => (
                  <option key={s} value={s}>
                    {ROTULO_SEVERIDADE[s]}
                  </option>
                ))}
              </select>
            </div>
          </div>
        }
      >
        {lista.error ? (
          <ErrorState titulo="Falha ao carregar os alertas" erro={lista.error} aoTentarNovamente={lista.recarregar} />
        ) : !lista.data ? (
          <LoadingState rotulo="Carregando alertas…" />
        ) : lista.data.itens.length === 0 ? (
          <EmptyState
            icone={CircleCheck}
            titulo={status === "ABERTO" && !severidade ? "Nenhum alerta aberto." : "Nenhum alerta com esses filtros."}
            descricao={
              status === "ABERTO" && !severidade
                ? "O monitoramento não encontrou nada que precise de atenção agora."
                : undefined
            }
          />
        ) : (
          <div className="flex flex-col gap-4">
            <ul aria-busy={lista.loading} className={lista.loading ? "opacity-60 transition-opacity" : ""}>
              {lista.data.itens.map((a) => (
                <LinhaAlerta key={a.id} alerta={a} />
              ))}
            </ul>
            <Pagination
              pagina={lista.data.pagina}
              totalPaginas={lista.data.total_paginas}
              totalRegistros={lista.data.total}
              tamanhoPagina={lista.data.tamanho_pagina}
              itensNaPagina={lista.data.itens.length}
              aoMudarPagina={setPagina}
              desabilitado={lista.loading}
            />
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
