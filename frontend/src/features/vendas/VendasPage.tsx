import { BadgeDollarSign, ChartColumn, Download, History, LoaderCircle, Package, Receipt, ShoppingCart, Store, Target, Ticket, Tv, Undo2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";

import { AppShell } from "../../components/layout/AppShell";
import { FiltroGlobalBar } from "../../components/layout/FiltroGlobalBar";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { AvisoFalhaAtualizacao } from "../../components/ui/AvisoFalhaAtualizacao";
import { EmptyState } from "../../components/ui/EmptyState";
import { MetricCard } from "../../components/ui/MetricCard";
import { Panel } from "../../components/ui/Panel";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { useAsync } from "../../hooks/useAsync";
import { useTemAba } from "../auth/AuthContext";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { gravarBusca, useBuscaDaUrl } from "../../hooks/useBuscaDaUrl";
import { useFiltroGlobal, type EstadoFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { escreverFiltroGlobal } from "../../lib/filtroGlobal";
import { hojeNoFuso } from "../../lib/periodo";
import {
  formatarDataHora,
  formatarMoeda,
  formatarMoedaNumero,
  formatarNumero,
  formatarQuantidade,
  nomeCurtoEmpresa,
  rotuloDia,
} from "../../lib/format";
import { getEmpresas } from "../../services/empresasService";
import { exportarFormasPagamento, getResumoVendas } from "../../services/vendasService";
import { baixarCsv } from "../../lib/csv";
import type { CanalVenda, ParamsVendas, ProdutoVendido, ResumoVendas, VendasPorVendedor } from "../../types/api";
import { ChartPanel } from "../../components/charts/ChartPanel";
import { GraficoCanais } from "./components/GraficoCanais";
import { GraficoCategorias } from "./components/GraficoCategorias";
import { GraficoFaturamento } from "./components/GraficoFaturamento";
import { GraficoFormasPagamento } from "./components/GraficoFormasPagamento";
import { GraficoQuantidade } from "./components/GraficoQuantidade";
import { ExportarDescontos } from "./components/ExportarDescontos";
import { FiltroDias } from "./components/FiltroDias";
import { ProdutosMaisVendidos } from "./components/ProdutosMaisVendidos";
import { RankingVendedores } from "./components/RankingVendedores";
import { VendasPorLoja } from "./components/VendasPorLoja";
import { aguardarTroca, useEscopoDeVendas, type AbaDeVendas } from "./lib/abasEmpresas";
import {
  CANAIS,
  descreverDias,
  ehCanal,
  lerDias,
  historicoIncompleto,
  paramsDasVendas,
  paraNumero,
  participacao,
  formatarPercentual,
  prepararSerie,
  variacaoDoTotal,
} from "./lib/vendas";

export const TITULO_VENDAS = "Painel de Vendas";
export const SUBTITULO_VENDAS = "Faturamento das notas fiscais de venda do ERP · somente consulta";


function useCanal(): [CanalVenda | null, (canal: CanalVenda | null) => void] {
  const busca = new URLSearchParams(useBuscaDaUrl());
  const valor = busca.get("canal");
  const canal = ehCanal(valor) ? valor : null;
  const definir = useCallback((novo: CanalVenda | null) => {
    const atual = new URLSearchParams(window.location.search);
    if (novo) atual.set("canal", novo);
    else atual.delete("canal");
    gravarBusca(atual, "push");
  }, []);
  return [canal, definir];
}


function useDias(): [string[], (dias: string[]) => void] {
  const texto = new URLSearchParams(useBuscaDaUrl()).get("dias");
  const dias = useMemo(() => lerDias(texto), [texto]);
  const definir = useCallback((novos: string[]) => {
    const atual = new URLSearchParams(window.location.search);
    if (novos.length) atual.set("dias", novos.join(","));
    else atual.delete("dias");
    gravarBusca(atual, "push");
  }, []);
  return [dias, definir];
}


function semDiasAoTrocarPeriodo(estado: EstadoFiltroGlobal, comDias: boolean): EstadoFiltroGlobal {
  if (!comDias) return estado;
  return {
    ...estado,
    definir: (novo) => {
      if (novo.empresa !== estado.filtro.empresa) return estado.definir(novo);
      const busca = escreverFiltroGlobal(new URLSearchParams(window.location.search), novo);
      busca.delete("dias");
      busca.delete("pagina");
      gravarBusca(busca, "push");
    },
  };
}

function FiltroCanal({ canal, aoMudar }: { canal: CanalVenda | null; aoMudar: (c: CanalVenda | null) => void }) {
  const opcoes: { valor: CanalVenda | null; rotulo: string }[] = [{ valor: null, rotulo: "Todos" }, ...CANAIS];
  return (
    <div className="flex items-center gap-2">
      <Store aria-hidden className="size-4 text-texto-mudo" />
      <div role="group" aria-label="Canal de venda" className="flex flex-wrap rounded-lg border border-borda bg-superficie-2 p-0.5">
        {opcoes.map((o) => {
          const ativo = o.valor === canal;
          return (
            <button
              key={o.rotulo}
              type="button"
              aria-pressed={ativo}
              onClick={() => aoMudar(o.valor)}
              className={`h-8 rounded-md px-3 text-xs font-semibold transition-colors sm:h-7 ${
                ativo ? "bg-texto text-superficie shadow-sm" : "text-texto-2 hover:bg-superficie-3 hover:text-texto"
              }`}
            >
              {o.rotulo}
            </button>
          );
        })}
      </div>
    </div>
  );
}


function AbasEmpresas({ abas, empresa, aoMudar }: { abas: AbaDeVendas[]; empresa: string; aoMudar: (codigo: string) => void }) {
  if (abas.length < 2) return null;
  return (
    <div role="tablist" aria-label="Vendas por empresa" className="flex gap-1 overflow-x-auto border-b border-borda">
      {abas.map((o) => (
        <button
          key={o.codigo || "geral"}
          type="button"
          role="tab"
          aria-selected={empresa === o.codigo}
          onClick={() => aoMudar(o.codigo)}
          className={`-mb-px shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${
            empresa === o.codigo ? "border-acento text-texto" : "border-transparent text-texto-mudo hover:text-texto"
          }`}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}


function descreverEscopo(descricaoPeriodo: string, resumo: ResumoVendas | null, codigoEmpresa: string, canal: CanalVenda | null) {
  const empresa = resumo?.filtro.empresa;
  const nomeEmpresa = empresa ? nomeCurtoEmpresa(empresa.nome) : codigoEmpresa ? `Empresa ${codigoEmpresa}` : "consolidado";
  const nomeCanal = CANAIS.find((c) => c.valor === canal)?.rotulo.toLowerCase();
  return [descricaoPeriodo, nomeEmpresa, nomeCanal].filter(Boolean).join(" · ");
}


export function VendasPage() {
  const comTv = useTemAba("VENDAS.TV");
  const [rodada, setRodada] = useState(0);
  const filtroGlobal = useFiltroGlobal();
  const [canal, definirCanal] = useCanal();
  const [dias, definirDias] = useDias();
  const busca = useBuscaDaUrl();
  const params = useValorEstavel(paramsDasVendas(filtroGlobal, canal, dias));

  const empresas = useAsync((s) => getEmpresas(s), [], rodada);
  const escopoDoPerfil = useEscopoDeVendas(empresas.data, filtroGlobal.filtro.empresa, empresas.loading && !empresas.data);
  const liberada = escopoDoPerfil.liberada;
  const resumo = useAsync((s) => (liberada ? getResumoVendas(params, s) : aguardarTroca<ResumoVendas>()), [params, liberada], rodada);
  const atualizar = useCallback(() => setRodada((r) => r + 1), []);
  useAtualizacaoAutomatica(atualizar);

  const dados = resumo.data;
  const rotuloComparacao = dias.length ? undefined : filtroGlobal.comparacao?.rotulo;
  const descricaoPeriodo = dias.length ? descreverDias(dias) : filtroGlobal.descricaoPeriodo;
  const escopo = descreverEscopo(descricaoPeriodo, dados, filtroGlobal.filtro.empresa, canal);
  const serie = useMemo(() => (dados ? prepararSerie(dados.serie, dados.granularidade) : []), [dados]);

  const carregando = resumo.loading && !dados;
  const atualizandoPaineis = resumo.loading && Boolean(dados);
  const erro = dados ? null : resumo.error;
  const semVendas = dados ? dados.totais.notas === 0 : false;
  const porMes = dados?.granularidade === "mes";
  const cobertura = dados?.cobertura;

  const header = (
    <Header
      titulo={TITULO_VENDAS}
      subtitulo={SUBTITULO_VENDAS}
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
      acoes={
        <div className="flex gap-2">
          <ExportarDescontos params={params} hoje={hojeNoFuso()} />
          <Link to="/vendas/metas" className="btn btn-secundario shrink-0" title="Metas do grupo, das lojas e dos vendedores">
            <Target aria-hidden className="size-4" />
            Metas
          </Link>
          {comTv && (
            <Link to={`/vendas/tv${busca}`} className="btn btn-secundario shrink-0" title="Tela cheia para monitor, com atualização automática">
              <Tv aria-hidden className="size-4" />
              Modo TV
            </Link>
          )}
        </div>
      }
      filtros={
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:gap-6">
          <FiltroGlobalBar
            estado={semDiasAoTrocarPeriodo(filtroGlobal, dias.length > 0)}
            empresas={escopoDoPerfil.empresasDoSeletor}
            carregandoEmpresas={empresas.loading && !empresas.data}
            semConsolidado={escopoDoPerfil.semConsolidado}
          />
          <FiltroCanal canal={canal} aoMudar={definirCanal} />
          <FiltroDias dias={dias} hoje={hojeNoFuso()} aoMudar={definirDias} />
        </div>
      }
    />
  );

  const variacao = (
    campo: "faturamento" | "faturamento_liquido" | "devolucoes" | "notas" | "ticket_medio" | "quantidade",
    sentido: "subir" | "descer" = "subir",
  ) => variacaoDoTotal(dados, campo, rotuloComparacao, sentido);


  const devolucoes = dados?.totais.devolucoes ?? null;
  const comDevolucoes = Boolean(dados) && devolucoes !== null;
  const formas = dados?.formas_pagamento ?? null;

  return (
    <AppShell header={header}>
      <AbasEmpresas
        abas={escopoDoPerfil.abas}
        empresa={filtroGlobal.filtro.empresa}
        aoMudar={(empresa) => filtroGlobal.definir({ ...filtroGlobal.filtro, empresa })}
      />
      <AvisoFalhaAtualizacao erro={dados ? resumo.error : null} aoTentarNovamente={resumo.recarregar} />
      {historicoIncompleto(dados) && (
        <p role="status" className="flex items-start gap-3 rounded-painel border border-info/30 bg-info/[0.06] px-4 py-3 text-sm text-texto-2">
          <History aria-hidden className="mt-0.5 size-4 shrink-0 text-info-texto" />
          <span>
            O histórico de vendas ainda está sendo carregado do ERP
            {cobertura?.desde ? ` (disponível desde ${rotuloDia(cobertura.desde)})` : ""}. Os totais deste período
            ficam completos quando a carga terminar.
          </span>
        </p>
      )}

      <section aria-labelledby="titulo-indicadores-vendas">
        <SectionHeader
          id="titulo-indicadores-vendas"
          titulo="Indicadores"
          descricao={rotuloComparacao ? `${escopo}. Setas comparam com ${rotuloComparacao}.` : escopo}
          icone={BadgeDollarSign}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
          <MetricCard
            rotulo={comDevolucoes || !dados ? "Faturamento líquido" : "Faturamento"}
            valor={
              dados ? formatarMoeda(comDevolucoes ? dados.totais.faturamento_liquido : dados.totais.faturamento) : undefined
            }
            detalhe={
              dados
                ? comDevolucoes
                  ? `Bruto ${formatarMoeda(dados.totais.faturamento)}`
                  : "Bruto: devoluções não têm canal"
                : undefined
            }
            destaque
            icone={BadgeDollarSign}
            dica="Notas de venda não canceladas (balcão, televendas e faturamento), menos as devoluções de venda do período."
            carregando={carregando}
            variacao={variacao(comDevolucoes ? "faturamento_liquido" : "faturamento")}
          />
          <MetricCard
            rotulo="Devoluções"
            valor={comDevolucoes && devolucoes !== null ? formatarMoeda(devolucoes) : undefined}
            detalhe={
              dados
                ? comDevolucoes && devolucoes !== null
                  ? `${formatarPercentual(participacao(paraNumero(devolucoes), paraNumero(dados.totais.faturamento)))} do faturamento bruto`
                  : "Não se aplica ao filtro de canal"
                : undefined
            }
            tom="critico"
            icone={Undo2}
            dica="Notas de entrada de devolução de venda (COI 30 e 31) do período. Não têm canal."
            carregando={carregando}
            variacao={comDevolucoes ? variacao("devolucoes", "descer") : null}
          />
          <MetricCard
            rotulo="Ticket médio"
            valor={dados?.totais.ticket_medio ? formatarMoeda(dados.totais.ticket_medio) : undefined}
            tom="info"
            icone={Ticket}
            dica="Faturamento dividido pelo número de notas."
            carregando={carregando}
            variacao={variacao("ticket_medio")}
          />
          <MetricCard
            rotulo="Notas de venda"
            valor={dados ? formatarNumero(dados.totais.notas) : undefined}
            tom="bom"
            icone={Receipt}
            dica="NFC-e do balcão e NF-e de televendas e do faturamento. Pedidos gerenciais não contam: viram nota depois."
            carregando={carregando}
            variacao={variacao("notas")}
          />
          <MetricCard
            rotulo="Quantidade vendida"
            valor={dados ? formatarQuantidade(String(Math.round(Number(dados.totais.quantidade)))) : undefined}
            tom="aviso"
            icone={Package}
            dica="Soma das quantidades dos itens, nas unidades de cada produto (un, kg, m, sacos...)."
            carregando={carregando}
            variacao={variacao("quantidade")}
          />
        </div>
      </section>

      <section aria-labelledby="titulo-analise-vendas">
        <SectionHeader
          id="titulo-analise-vendas"
          titulo="Análise"
          descricao={
            cobertura?.desde
              ? `Histórico desde ${rotuloDia(cobertura.desde)} · dados lidos em ${formatarDataHora(cobertura.atualizado_em)}`
              : escopo
          }
          icone={ChartColumn}
        />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ChartPanel
              titulo="Evolução do faturamento"
              subtitulo={`${comDevolucoes ? "Líquido de devoluções" : "Bruto"}, ${porMes ? "por mês" : "por dia"}`}
              carregando={carregando}
              atualizando={atualizandoPaineis}
              erro={erro}
              vazio={semVendas}
              mensagemVazio="Nenhuma venda no período."
              aoTentarNovamente={resumo.recarregar}
              descricao={serie.map((p) => `${p.rotuloCompleto}: ${formatarMoedaNumero(p.faturamento)}`).join(", ")}
            >
              <GraficoFaturamento dados={serie} />
            </ChartPanel>
          </div>
          <ChartPanel
            titulo="Vendas por canal"
            subtitulo="Participação no faturamento"
            carregando={carregando}
            atualizando={atualizandoPaineis}
            erro={erro}
            vazio={semVendas}
            mensagemVazio="Nenhuma venda no período."
            aoTentarNovamente={resumo.recarregar}
          >
            {dados && <GraficoCanais dados={dados.por_canal} />}
          </ChartPanel>

          <div className="lg:col-span-2">
            <ChartPanel
              titulo="Quantidade de produtos vendidos"
              subtitulo={`Soma das quantidades dos itens, ${porMes ? "por mês" : "por dia"}`}
              carregando={carregando}
              atualizando={atualizandoPaineis}
              erro={erro}
              vazio={semVendas}
              mensagemVazio="Nenhuma venda no período."
              aoTentarNovamente={resumo.recarregar}
            >
              <GraficoQuantidade dados={serie} />
            </ChartPanel>
          </div>
          <ChartPanel
            titulo="Formas de pagamento"
            subtitulo="Recebimentos do caixa no período"
            carregando={carregando}
            atualizando={atualizandoPaineis}
            erro={erro}
            vazio={!formas || formas.length === 0}
            mensagemVazio={
              dados && formas === null
                ? "Os recebimentos não têm canal: escolha Todos no filtro de canal."
                : "Nenhum recebimento no período (o histórico de pagamentos ainda pode estar carregando)."
            }
            aoTentarNovamente={resumo.recarregar}
            acao={formas && formas.length > 0 ? <BotaoExcelFormas params={params} /> : undefined}
          >
            {formas && <GraficoFormasPagamento dados={formas} />}
          </ChartPanel>
        </div>
      </section>

      <section aria-labelledby="titulo-ranking-vendas">
        <SectionHeader id="titulo-ranking-vendas" titulo="Rankings" descricao={escopo} icone={ShoppingCart} />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartPanel
            titulo="Vendas por categoria"
            subtitulo="Faturamento bruto por divisão do cadastro de produtos"
            carregando={carregando}
            atualizando={atualizandoPaineis}
            erro={erro}
            vazio={semVendas}
            mensagemVazio="Nenhuma venda no período."
            aoTentarNovamente={resumo.recarregar}
          >
            {dados && <GraficoCategorias dados={dados.por_categoria} />}
          </ChartPanel>
          <Panel titulo="Vendas por loja" subtitulo="Faturamento bruto, participação, notas e ticket médio">
            {dados && dados.por_empresa.length > 0 ? (
              <VendasPorLoja dados={dados.por_empresa} />
            ) : (
              <EmptyState titulo={carregando ? "Carregando…" : "Nenhuma venda no período"} />
            )}
          </Panel>
          <Panel
            titulo="Vendedores"
            subtitulo="Faturamento bruto por vendedor das notas; a linha na barra marca a média por vendedor"
            className="lg:col-span-2"
            acao={
              dados && dados.vendedores.vendedores.length > 0 ? (
                <BotaoCsv aoClicar={() => exportarVendedores(dados.vendedores.vendedores)} />
              ) : undefined
            }
          >
            {dados && dados.vendedores.vendedores.length > 0 ? (
              <RankingVendedores dados={dados.vendedores} rotuloComparacao={rotuloComparacao} />
            ) : (
              <EmptyState titulo={carregando ? "Carregando…" : "Nenhuma venda no período"} />
            )}
          </Panel>
          <Panel
            titulo="Produtos mais vendidos"
            subtitulo="Os 10 de maior faturamento bruto"
            className="lg:col-span-2"
            acao={dados && dados.produtos.length > 0 ? <BotaoCsv aoClicar={() => exportarProdutos(dados.produtos)} /> : undefined}
          >
            {dados && dados.produtos.length > 0 ? (
              <ProdutosMaisVendidos dados={dados.produtos} />
            ) : (
              <EmptyState titulo={carregando ? "Carregando…" : "Nenhuma venda no período"} />
            )}
          </Panel>
        </div>
      </section>
    </AppShell>
  );
}

function BotaoCsv({ aoClicar }: { aoClicar: () => void }) {
  return (
    <button type="button" className="btn btn-fantasma btn-sm" onClick={aoClicar} title="Baixar em CSV (abre no Excel)">
      <Download aria-hidden className="size-3.5" />
      CSV
    </button>
  );
}


function BotaoExcelFormas({ params }: { params: ParamsVendas }) {
  const [baixando, setBaixando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const exportar = async () => {
    setBaixando(true);
    setErro(null);
    try {
      await exportarFormasPagamento(params);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível exportar.");
    } finally {
      setBaixando(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        className="btn btn-fantasma btn-sm"
        onClick={exportar}
        disabled={baixando}
        title="Baixar em Excel (.xlsx), com o gráfico e as quantidades"
      >
        {baixando ? <LoaderCircle aria-hidden className="size-3.5 animate-spin" /> : <Download aria-hidden className="size-3.5" />}
        {baixando ? "Gerando..." : "Excel"}
      </button>
      {erro && (
        <p role="status" className="max-w-56 text-right text-[11px] text-aviso-texto">
          {erro}
        </p>
      )}
    </div>
  );
}

function exportarVendedores(vendedores: VendasPorVendedor[]) {
  baixarCsv(
    "vendas_vendedores",
    ["Código", "Nome", "Lojas", "Faturamento", "Notas", "Ticket médio", "Faturamento comparação", "Abaixo da média"],
    vendedores.map((v) => [
      v.id_vendedor,
      v.nome,
      v.empresas.map((e) => e.codigo).join(", "),
      v.faturamento,
      v.notas,
      v.ticket_medio,
      v.faturamento_comparacao,
      v.abaixo_da_media ? "sim" : "não",
    ]),
  );
}

function exportarProdutos(produtos: ProdutoVendido[]) {
  baixarCsv(
    "vendas_produtos",
    ["Produto", "Subproduto", "Descrição", "Quantidade", "Faturamento"],
    produtos.map((p) => [p.id_produto, p.id_subproduto, p.descricao, p.quantidade, p.faturamento]),
  );
}

