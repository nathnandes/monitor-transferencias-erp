import { ArrowLeftRight, Building, CircleAlert, CircleCheck, Clock, Database, RefreshCw, TriangleAlert } from "lucide-react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { MetricCard } from "../../../components/ui/MetricCard";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { descreverErro } from "../../../lib/erros";
import { formatarDataHora, formatarNumero, tempoRelativo } from "../../../lib/format";
import { ROTULO_SINCRONIZACAO, tomDaSincronizacao } from "../../../lib/status";
import { resumoVazio } from "../../../services/dashboardService";
import type { ResumoDashboard } from "../../../types/api";
import { variacaoDoFluxo } from "../../../lib/resumoFiltrado";

interface MetricsGridProps {
  resumo: ResumoDashboard | null;
  carregando: boolean;
  erro: Error | null;
  aoTentarNovamente: () => void;

  rotuloComparacao?: string;

  escopo?: string;
}

function percentual(parte: number, total: number): string | undefined {
  if (!total) return undefined;
  return `${Math.round((parte / total) * 100)}% do total`;
}


function detalheEmpresas(resumo: ResumoDashboard): string {
  const criticas = resumo.status_por_empresa.filter((s) => s.status === "critico").length;
  const atencao = resumo.status_por_empresa.filter((s) => s.status === "atencao").length;
  if (!criticas && !atencao) return "Todas sem pendências de atenção";
  const partes: string[] = [];
  if (criticas) partes.push(`${criticas} ${criticas === 1 ? "crítica" : "críticas"}`);
  if (atencao) partes.push(`${atencao} em atenção`);
  return partes.join(" · ");
}


export function MetricsGrid({ resumo, carregando, erro, aoTentarNovamente, rotuloComparacao, escopo }: MetricsGridProps) {

  if (erro && !resumo) {
    return <ErrorState titulo="Não foi possível carregar o resumo" erro={erro} aoTentarNovamente={aoTentarNovamente} />;
  }

  if (resumo && resumoVazio(resumo)) {
    return (
      <div className="rounded-painel border border-borda bg-superficie">
        <EmptyState
          icone={Database}
          titulo="Nenhum dado operacional no banco"
          descricao="Não há transferências, empresas ativas nem sincronizações. Em desenvolvimento, rode o seed de dados simulados no backend."
        />
      </div>
    );
  }

  const t = resumo?.transferencias;
  const atual = resumo?.situacao_atual;
  const horasAtencao = resumo?.limites_pendencia.horas_atencao;
  const fluxo = resumo?.periodo ?? null;
  const sinc = resumo?.ultima_sincronizacao;
  const esperando = carregando && !resumo;
  const processadas = fluxo ? fluxo.processadas : t?.processadas;

  return (
    <div className="flex flex-col gap-3">
      {/* Erro numa recarga: mantém os últimos dados e avisa que podem estar desatualizados. */}
      {erro && resumo && (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-critico/40 bg-critico/10 px-3 py-2 text-xs text-texto-2"
        >
          <TriangleAlert aria-hidden className="size-4 shrink-0 text-critico-texto" />
          <span className="min-w-0 flex-1">
            <strong className="font-medium text-critico-texto">Falha ao atualizar:</strong> {erro.message} Exibindo os
            últimos dados recebidos.{" "}
            <span className="whitespace-nowrap text-texto-mudo">({descreverErro(erro).rotulo})</span>
          </span>
          <button type="button" onClick={aoTentarNovamente} className="btn btn-sm btn-secundario">
            Tentar novamente
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 2xl:grid-cols-6 sm:gap-4">
        <MetricCard
          rotulo="Transferências criadas"
          destaque
          icone={ArrowLeftRight}
          dica="Transferências criadas no período escolhido no topo, em qualquer status. Com uma empresa escolhida, contam as que ela envia ou recebe."
          valor={t && formatarNumero(t.total)}
          variacao={variacaoDoFluxo(resumo, "criadas", rotuloComparacao, "neutro")}
          detalhe={t && (escopo ?? "Todas as empresas")}
          carregando={esperando}
        />
        <MetricCard
          rotulo="Processadas"
          tom="bom"
          icone={CircleCheck}
          dica="Transferências processadas no período (pela data de processamento), mesmo que criadas antes. Sem período, todas com status PROCESSADA."
          valor={processadas !== undefined ? formatarNumero(processadas) : undefined}
          variacao={variacaoDoFluxo(resumo, "processadas", rotuloComparacao, "subir")}
          detalhe={t && !fluxo ? percentual(t.processadas, t.total) : undefined}
          carregando={esperando}
        />
        <MetricCard
          rotulo="Pendentes agora"
          tom="aviso"
          icone={Clock}
          dica="Transferências com status PENDENTE neste momento, de qualquer data: uma pendência antiga continua valendo hoje. Não há comparação porque o sistema ainda não grava como estava em dias anteriores."
          valor={atual && formatarNumero(atual.pendentes)}
          detalhe={
            atual &&
            (atual.pendentes_atrasadas
              ? `${formatarNumero(atual.pendentes_atrasadas)} há mais de ${horasAtencao}h · de qualquer data`
              : `Nenhuma há mais de ${horasAtencao}h · de qualquer data`)
          }
          carregando={esperando}
        />
        <MetricCard
          rotulo="Com erro agora"
          tom="critico"
          icone={CircleAlert}
          dica="Transferências com status ERRO neste momento, de qualquer data. Abra Transferências filtrando por ERRO para ver cada uma."
          valor={atual && formatarNumero(atual.com_erro)}
          detalhe={atual && "De qualquer data"}
          carregando={esperando}
        />
        <MetricCard
          rotulo="Empresas ativas"
          tom="info"
          icone={Building}
          dica="Empresas ativas no cadastro. A situação (crítica, em atenção) é calculada pelo backend a partir de pendências e erros."
          valor={resumo && formatarNumero(resumo.empresas_ativas)}
          detalhe={resumo && detalheEmpresas(resumo)}
          carregando={esperando}
        />
        <MetricCard
          rotulo="Última sincronização"
          tom={sinc ? tomDaSincronizacao(sinc.status) : "neutro"}
          icone={RefreshCw}
          dica="Início da sincronização mais recente, em relação ao momento em que o resumo foi gerado."
          valor={
            resumo && (
              <span className="text-[1.625rem]">
                {sinc ? tempoRelativo(sinc.inicio, new Date(resumo.gerado_em)) : "Nenhuma"}
              </span>
            )
          }
          detalhe={
            sinc ? (
              <div className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge tom={tomDaSincronizacao(sinc.status)}>
                    {ROTULO_SINCRONIZACAO[sinc.status] ?? sinc.status}
                  </StatusBadge>
                  <span>{sinc.empresa ? `Empresa ${sinc.empresa.codigo}` : "Global"}</span>
                </div>
                <span className="text-texto-mudo" title={sinc.mensagem_erro ?? undefined}>
                  {formatarDataHora(sinc.inicio)}
                </span>
              </div>
            ) : (
              resumo && "Sem registro de sincronização"
            )
          }
          carregando={esperando}
        />
      </div>
    </div>
  );
}
