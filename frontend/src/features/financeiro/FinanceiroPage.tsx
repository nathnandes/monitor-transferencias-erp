import {
  BadgeDollarSign,
  CalendarClock,
  CircleCheck,
  Clock,
  FileText,
  HandCoins,
  History,
  ListChecks,
  Wallet,
} from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import { ChartPanel } from "../../components/charts/ChartPanel";
import { AppShell } from "../../components/layout/AppShell";
import { FiltroGlobalBar } from "../../components/layout/FiltroGlobalBar";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { AvisoFalhaAtualizacao } from "../../components/ui/AvisoFalhaAtualizacao";
import { MetricCard } from "../../components/ui/MetricCard";
import { Panel } from "../../components/ui/Panel";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { useAsync } from "../../hooks/useAsync";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import {
  formatarDataHora,
  formatarMoeda,
  formatarMoedaNumero,
  formatarNumero,
  nomeCurtoEmpresa,
  rotuloDia,
} from "../../lib/format";
import { getEmpresas } from "../../services/empresasService";
import { getResumoFinanceiro } from "../../services/financeiroService";
import type {
  ParamsFinanceiro,
  ResumoFinanceiro,
} from "../../types/api";
import {
  formatarPercentual,
  lojasQueVendem,
  paraNumero,
  participacao,
} from "./lib/financeiro";
import { GraficoVendidoPorForma } from "./components/GraficoVendidoPorForma";
import { RecebidosPorForma } from "./components/RecebidosPorForma";
import { TabelaParcelas } from "./components/TabelaParcelas";

export const TITULO_FINANCEIRO = "Financeiro";
export const SUBTITULO_FINANCEIRO =
  "Vendido, pago, pendente e recebido por forma de pagamento · somente consulta";

function descreverEscopo(
  descricaoPeriodo: string,
  resumo: ResumoFinanceiro | null,
  codigoEmpresa: string,
) {
  const empresa = resumo?.filtro.empresa;
  const nome = empresa
    ? nomeCurtoEmpresa(empresa.nome)
    : codigoEmpresa
      ? `Empresa ${codigoEmpresa}`
      : "consolidado";
  return `${descricaoPeriodo} · ${nome}`;
}


function historicoIncompleto(resumo: ResumoFinanceiro | null): boolean {
  const desde = resumo?.cobertura.desde;
  const inicio = resumo?.filtro.data_inicial;
  if (!resumo) return false;
  if (!desde) return true;
  return !inicio || inicio < desde;
}


export function FinanceiroPage() {
  const [rodada, setRodada] = useState(0);
  const filtroGlobal = useFiltroGlobal();
  const { filtro, intervalo } = filtroGlobal;
  const params = useValorEstavel<ParamsFinanceiro>({
    empresa: filtro.empresa || undefined,
    data_inicial: intervalo?.inicio,
    data_final: intervalo?.fim,
  });

  const empresas = useAsync((s) => getEmpresas(s), [], rodada);
  const lojas = useMemo(
    () =>
      empresas.loading && !empresas.data ? null : lojasQueVendem(empresas.data),
    [empresas.loading, empresas.data],
  );
  const resumo = useAsync(
    (s) => getResumoFinanceiro(params, s),
    [params],
    rodada,
  );
  const atualizar = useCallback(() => setRodada((r) => r + 1), []);
  useAtualizacaoAutomatica(atualizar);

  const dados = resumo.data;
  const carregando = resumo.loading && !dados;
  const atualizandoPaineis = resumo.loading && Boolean(dados);
  const erro = dados ? null : resumo.error;
  const escopo = descreverEscopo(
    filtroGlobal.descricaoPeriodo,
    dados,
    filtro.empresa,
  );
  const cobertura = dados?.cobertura;

  const vendido = paraNumero(dados?.vendas.valor ?? "0");
  const pago = paraNumero(dados?.vendas.valor_pago ?? "0");
  const pendente = paraNumero(dados?.vendas.valor_pendente ?? "0");
  const recebido = paraNumero(dados?.recebidos.total ?? "0");
  const doPeriodo = paraNumero(dados?.recebidos.das_vendas_do_periodo ?? "0");
  const boletos = paraNumero(dados?.recebidos.de_boletos ?? "0");
  const outros = paraNumero(dados?.recebidos.outros_anteriores ?? "0");
  const formasDoPeriodo = useMemo(
    () =>
      [
        ...new Set([
          ...(dados?.vendas.formas ?? []).map((f) => f.forma),
          ...(dados?.recebidos.formas ?? []).map((f) => f.forma),
        ]),
      ].sort(),
    [dados],
  );
  const juros = paraNumero(dados?.recebidos.juros ?? "0");
  const mensagemVazio =
    "Nada no período (o histórico de pagamentos ainda pode estar carregando).";

  const header = (
    <Header
      titulo={TITULO_FINANCEIRO}
      subtitulo={SUBTITULO_FINANCEIRO}
      info={
        <IndicadorAtualizacao
          atualizadoEm={resumo.atualizadoEm}
          geradoEm={cobertura?.atualizado_em ?? null}
          atualizando={resumo.loading}
          fontes={["vendas"]}
        />
      }
      aoAtualizar={atualizar}
      atualizando={resumo.loading || empresas.loading}
      filtros={
        <FiltroGlobalBar
          estado={filtroGlobal}
          empresas={lojas}
          carregandoEmpresas={lojas === null}
        />
      }
    />
  );

  return (
    <AppShell header={header}>
      <AvisoFalhaAtualizacao
        erro={dados ? resumo.error : null}
        aoTentarNovamente={resumo.recarregar}
      />
      {historicoIncompleto(dados) && (
        <p
          role="status"
          className="flex items-start gap-3 rounded-painel border border-info/30 bg-info/[0.06] px-4 py-3 text-sm text-texto-2"
        >
          <History
            aria-hidden
            className="mt-0.5 size-4 shrink-0 text-info-texto"
          />
          <span>
            O histórico de pagamentos ainda está sendo carregado do ERP
            {cobertura?.desde
              ? ` (disponível desde ${rotuloDia(cobertura.desde)})`
              : ""}
            . Os totais deste período ficam completos quando a carga terminar.
          </span>
        </p>
      )}

      <section aria-labelledby="titulo-vendas-pagas">
        <SectionHeader
          id="titulo-vendas-pagas"
          titulo="Vendas do período"
          descricao={`${escopo}. Pago e pendente até a última leitura do ERP.`}
          icone={BadgeDollarSign}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <MetricCard
            rotulo="Vendido"
            valor={dados ? formatarMoeda(dados.vendas.valor) : undefined}
            detalhe={
              dados
                ? `${formatarNumero(dados.vendas.parcelas)} parcelas`
                : undefined
            }
            destaque
            icone={BadgeDollarSign}
            dica="Parcelas das vendas do caixa (série PDV) lançadas no período, em todas as formas de pagamento."
            carregando={carregando}
          />
          <MetricCard
            rotulo="Já pago"
            valor={dados ? formatarMoeda(dados.vendas.valor_pago) : undefined}
            detalhe={
              dados
                ? `${formatarPercentual(participacao(pago, vendido))} do vendido`
                : undefined
            }
            tom="bom"
            icone={CircleCheck}
            dica="Quanto dessas parcelas já foi pago: PIX e cartão no ato, boleto quando o cliente paga."
            carregando={carregando}
          />
          <MetricCard
            rotulo="Pendente"
            valor={
              dados ? formatarMoeda(dados.vendas.valor_pendente) : undefined
            }
            detalhe={
              dados
                ? `${formatarPercentual(participacao(pendente, vendido))} do vendido`
                : undefined
            }
            tom="aviso"
            icone={Clock}
            dica="Quanto dessas parcelas ainda falta pagar (boletos a vencer ou vencidos, por exemplo)."
            carregando={carregando}
          />
        </div>
      </section>

      <section aria-labelledby="titulo-recebidos">
        <SectionHeader
          id="titulo-recebidos"
          titulo="Recebido no período"
          descricao="Pela data do último recebimento de cada parcela, de qualquer venda."
          icone={HandCoins}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            rotulo="Recebido"
            valor={dados ? formatarMoeda(dados.recebidos.total) : undefined}
            detalhe={
              dados
                ? `${formatarNumero(dados.recebidos.titulos)} parcelas${juros > 0 ? ` · juros ${formatarMoedaNumero(juros)}` : ""}`
                : undefined
            }
            destaque
            icone={Wallet}
            dica="O que entrou no período: vendas do período + boletos + outros a prazo de antes. Os juros vêm à parte."
            carregando={carregando}
          />
          <MetricCard
            rotulo="Das vendas do período"
            valor={dados ? formatarMoeda(dados.recebidos.das_vendas_do_periodo) : undefined}
            detalhe={
              dados ? `${formatarPercentual(participacao(doPeriodo, recebido))} do recebido` : undefined
            }
            tom="info"
            icone={CircleCheck}
            dica="Pago de vendas lançadas no período, fora boleto: PIX, cartão, dinheiro..."
            carregando={carregando}
          />
          <MetricCard
            rotulo="De boletos"
            valor={dados ? formatarMoeda(dados.recebidos.de_boletos) : undefined}
            detalhe={
              dados ? `${formatarPercentual(participacao(boletos, recebido))} do recebido` : undefined
            }
            tom="info"
            icone={FileText}
            dica="Boletos pagos no período (todas as contas), de qualquer venda: a do período ou de meses antes."
            carregando={carregando}
          />
          <MetricCard
            rotulo="Outros a prazo de antes"
            valor={dados ? formatarMoeda(dados.recebidos.outros_anteriores) : undefined}
            detalhe={
              dados ? `${formatarPercentual(participacao(outros, recebido))} do recebido` : undefined
            }
            tom="info"
            icone={CalendarClock}
            dica="Fora boleto, lançados antes do período e pagos nele: transferência a receber, receber na entrega..."
            carregando={carregando}
          />
        </div>
      </section>

      <section aria-labelledby="titulo-formas-financeiro">
        <SectionHeader
          id="titulo-formas-financeiro"
          titulo="Por forma de pagamento"
          descricao={
            cobertura?.desde
              ? `Histórico desde ${rotuloDia(cobertura.desde)} · dados lidos em ${formatarDataHora(cobertura.atualizado_em)}`
              : escopo
          }
          icone={Wallet}
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartPanel
            titulo="Vendido por forma"
            subtitulo="Vendas do período; o pago e o pendente de cada forma no destaque"
            carregando={carregando}
            atualizando={atualizandoPaineis}
            erro={erro}
            vazio={!dados || dados.vendas.formas.length === 0}
            mensagemVazio={mensagemVazio}
            aoTentarNovamente={resumo.recarregar}
          >
            {dados && <GraficoVendidoPorForma dados={dados.vendas.formas} />}
          </ChartPanel>
          <ChartPanel
            titulo="Recebido por forma"
            subtitulo="O que entrou no período, das vendas dele e de anteriores"
            carregando={carregando}
            atualizando={atualizandoPaineis}
            erro={erro}
            vazio={!dados || dados.recebidos.formas.length === 0}
            mensagemVazio={mensagemVazio}
            aoTentarNovamente={resumo.recarregar}
          >
            {dados && <RecebidosPorForma dados={dados.recebidos.formas} />}
          </ChartPanel>
        </div>
      </section>

      <section aria-labelledby="titulo-parcelas">
        <SectionHeader
          id="titulo-parcelas"
          titulo="Parcela por parcela"
          descricao="Cada parcela como veio do ERP, para conferir o pago e o pendente com o relatório de títulos de lá."
          icone={ListChecks}
        />
        <Panel>
          <TabelaParcelas base={params} formas={formasDoPeriodo} rodada={rodada} />
        </Panel>
      </section>
    </AppShell>
  );
}
