import { ArrowLeftRight, CircleAlert, CircleCheck, Clock, Siren, WifiOff, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { AvisoSemCoi } from "../../components/layout/AvisoSemCoi";
import { IndicadorVariacao } from "../../components/ui/IndicadorVariacao";
import { useAsync } from "../../hooks/useAsync";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { formatarHoraMinuto, formatarNumero } from "../../lib/format";
import { getResumoDashboard } from "../../services/dashboardService";
import { descreverEscopo, paramsDoResumo, variacaoDoFluxo, type VariacaoRotulada } from "../../lib/resumoFiltrado";
import { CabecalhoTv } from "../../components/layout/CabecalhoTv";


export const INTERVALO_TV_MS = 60_000;


export function TvPage() {
  const filtroGlobal = useFiltroGlobal();
  const params = useValorEstavel(paramsDoResumo(filtroGlobal));
  const resumo = useAsync((s) => getResumoDashboard(params, s), [params]);
  const { recarregar } = resumo;

  useAtualizacaoAutomatica(recarregar, INTERVALO_TV_MS);

  const dados = resumo.data;
  const rotulo = filtroGlobal.comparacao?.rotulo;
  const escopo = descreverEscopo(filtroGlobal.descricaoPeriodo, dados, filtroGlobal.filtro.empresa);
  const criticas = dados?.status_por_empresa.filter((s) => s.status === "critico") ?? [];
  const atual = dados?.situacao_atual;
  const horasAtencao = dados?.limites_pendencia.horas_atencao;

  return (
    <div className="tema-escuro flex min-h-dvh flex-col gap-[2vh] bg-plano px-[3vw] py-[3vh] text-texto">
      <CabecalhoTv titulo="Painel ao vivo" escopo={escopo} atualizadoEm={resumo.atualizadoEm} saida={`/dashboard${filtroGlobal.query}`} />

      {resumo.error && (
        <p role="alert" className="flex items-center gap-3 rounded-lg border border-critico/50 bg-critico/15 px-4 py-3 text-[clamp(0.9rem,2vh,1.3rem)] text-critico-texto">
          <WifiOff aria-hidden className="size-6 shrink-0" />
          {dados
            ? `Sem conexão com o servidor. Exibindo os dados das ${resumo.atualizadoEm ? formatarHoraMinuto(resumo.atualizadoEm) : "última leitura"}; nova tentativa em até 1 minuto.`
            : `Não foi possível carregar os indicadores: ${resumo.error.message}`}
        </p>
      )}

      <AvisoSemCoi variante="tv" />

      <main className="grid flex-1 grid-cols-1 gap-[2vh] md:grid-cols-6">
        <Indicador
          className="md:col-span-3"
          rotulo="Transferências criadas"
          icone={ArrowLeftRight}
          destaque
          valor={dados?.transferencias.total}
          variacao={variacaoDoFluxo(dados, "criadas", rotulo, "neutro")}
        />
        <Indicador
          className="md:col-span-3"
          rotulo="Processadas"
          icone={CircleCheck}
          valor={dados ? (dados.periodo?.processadas ?? dados.transferencias.processadas) : undefined}
          variacao={variacaoDoFluxo(dados, "processadas", rotulo, "subir")}
        />
        <Indicador
          className="md:col-span-2"
          rotulo="Pendentes agora"
          icone={Clock}
          alerta={Boolean(atual?.pendentes_atrasadas)}
          valor={atual?.pendentes}
          detalhe={
            atual &&
            (atual.pendentes_atrasadas
              ? `${formatarNumero(atual.pendentes_atrasadas)} há mais de ${horasAtencao}h`
              : `Nenhuma há mais de ${horasAtencao}h`)
          }
        />
        <Indicador
          className="md:col-span-2"
          rotulo="Com erro agora"
          icone={CircleAlert}
          alerta={Boolean(atual?.com_erro)}
          valor={atual?.com_erro}
          detalhe={atual && (atual.com_erro ? "Precisam de atenção" : "Nenhum erro")}
        />
        <Indicador
          className="md:col-span-2"
          rotulo="Empresas em situação crítica"
          icone={Siren}
          alerta={criticas.length > 0}
          valor={dados ? criticas.length : undefined}
          detalhe={dados && (criticas.length ? `Lojas ${criticas.map((c) => c.empresa.codigo).join(" · ")}` : "Todas em dia")}
        />
      </main>
    </div>
  );
}

interface IndicadorProps {
  rotulo: string;
  icone: LucideIcon;
  valor: number | undefined;
  variacao?: VariacaoRotulada | null;
  detalhe?: ReactNode;

  alerta?: boolean;
  destaque?: boolean;
  className?: string;
}

function Indicador({ rotulo, icone: Icone, valor, variacao, detalhe, alerta = false, destaque = false, className = "" }: IndicadorProps) {
  const borda = alerta ? "border-critico" : destaque ? "border-acento" : "border-borda-forte";
  return (
    <article className={`flex flex-col justify-between rounded-painel border-2 bg-superficie p-[2.5vh] ${borda} ${className}`}>
      <h2 className="marca-apoio flex items-center gap-3 text-[clamp(0.9rem,2.2vh,1.6rem)] text-texto-2">
        <Icone aria-hidden className={`size-[1.4em] shrink-0 ${alerta ? "text-critico-texto" : "text-acento"}`} />
        {rotulo}
      </h2>
      <p className={`tabular font-display text-[clamp(3.5rem,13vh,10rem)] font-extrabold leading-none ${alerta ? "text-critico-texto" : "text-texto"}`}>
        {valor === undefined ? "—" : formatarNumero(valor)}
      </p>
      <div className="flex flex-col gap-1 text-[clamp(0.9rem,2.2vh,1.6rem)]">
        {variacao && <IndicadorVariacao variacao={variacao.valor} rotulo={variacao.rotulo} />}
        {detalhe && <p className="text-texto-2">{detalhe}</p>}
      </div>
    </article>
  );
}
