import { BadgeDollarSign, Medal, Receipt, Store, Ticket, Trophy, WifiOff, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import type { Variacao } from "../../lib/variacao";
import { useAsync } from "../../hooks/useAsync";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { useBuscaDaUrl } from "../../hooks/useBuscaDaUrl";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { formatarHoraMinuto, formatarMoeda, formatarNumero, nomeCurtoEmpresa } from "../../lib/format";
import { getResumoVendas } from "../../services/vendasService";
import type { ResumoVendas, VendasPorVendedor } from "../../types/api";
import { IndicadorVariacao } from "../../components/ui/IndicadorVariacao";
import { CabecalhoTv } from "../../components/layout/CabecalhoTv";
import {
  CANAIS,
  ehCanal,
  formatarPercentual,
  nomeProprio,
  lerDias,
  descreverDias,
  paramsDasVendas,
  paraNumero,
  participacao,
  variacaoDoTotal,
} from "./lib/vendas";
import { aguardarTroca, useEscopoDeVendas } from "./lib/abasEmpresas";


export const INTERVALO_VENDAS_TV_MS = 60_000;


export const VENDEDORES_NA_TV = 5;


export function VendasTvPage() {
  const busca = useBuscaDaUrl();
  const valorCanal = new URLSearchParams(busca).get("canal");
  const canal = ehCanal(valorCanal) ? valorCanal : null;
  const filtroGlobal = useFiltroGlobal();

  const { liberada } = useEscopoDeVendas(null, filtroGlobal.filtro.empresa);
  const dias = lerDias(new URLSearchParams(busca).get("dias"));
  const params = useValorEstavel(paramsDasVendas(filtroGlobal, canal, dias));
  const resumo = useAsync((s) => (liberada ? getResumoVendas(params, s) : aguardarTroca<ResumoVendas>()), [params, liberada]);

  useAtualizacaoAutomatica(resumo.recarregar, INTERVALO_VENDAS_TV_MS);

  const dados = resumo.data;
  const rotulo = dias.length ? undefined : filtroGlobal.comparacao?.rotulo;
  const escopo = descreverEscopo(dias.length ? descreverDias(dias) : filtroGlobal.descricaoPeriodo, dados, filtroGlobal.filtro.empresa, canal);

  const comDevolucoes = dados ? dados.totais.devolucoes !== null : true;
  const faturamento = dados ? (comDevolucoes ? dados.totais.faturamento_liquido : dados.totais.faturamento) : undefined;

  return (
    <div className="tema-escuro flex min-h-dvh flex-col gap-[2vh] bg-plano px-[3vw] py-[3vh] text-texto">
      <CabecalhoTv titulo="Vendas ao vivo" escopo={escopo} atualizadoEm={resumo.atualizadoEm} saida={`/vendas${busca}`} />

      {resumo.error && (
        <p role="alert" className="flex items-center gap-3 rounded-lg border border-critico/50 bg-critico/15 px-4 py-3 text-[clamp(0.9rem,2vh,1.3rem)] text-critico-texto">
          <WifiOff aria-hidden className="size-6 shrink-0" />
          {dados
            ? `Sem conexão com o servidor. Exibindo os dados das ${resumo.atualizadoEm ? formatarHoraMinuto(resumo.atualizadoEm) : "última leitura"}; nova tentativa em até 1 minuto.`
            : `Não foi possível carregar as vendas: ${resumo.error.message}`}
        </p>
      )}

      <main className="grid flex-1 grid-cols-1 gap-[2vh] md:grid-cols-6">
        <Indicador
          className="md:col-span-6 xl:col-span-3"
          rotulo={comDevolucoes ? "Faturamento líquido" : "Faturamento"}
          icone={BadgeDollarSign}
          destaque
          valor={faturamento === undefined ? undefined : formatarMoeda(faturamento)}
          variacao={variacaoDoTotal(dados, comDevolucoes ? "faturamento_liquido" : "faturamento", rotulo)}
          detalhe={
            dados &&
            (comDevolucoes
              ? `Bruto ${formatarMoeda(dados.totais.faturamento)} · devoluções ${formatarMoeda(dados.totais.devolucoes)}`
              : "Bruto: devoluções não têm canal")
          }
        />
        <Indicador
          className="md:col-span-3 xl:col-span-2"
          rotulo="Ticket médio"
          icone={Ticket}
          valor={dados ? formatarMoeda(dados.totais.ticket_medio) : undefined}
          variacao={variacaoDoTotal(dados, "ticket_medio", rotulo)}
        />
        <Indicador
          className="md:col-span-3 xl:col-span-1"
          rotulo="Notas"
          icone={Receipt}
          valor={dados ? formatarNumero(dados.totais.notas) : undefined}
          variacao={variacaoDoTotal(dados, "notas", rotulo)}
        />

        <Quadro className="md:col-span-6 xl:col-span-3" titulo="Melhores vendedores" icone={Trophy}>
          {dados && dados.vendedores.vendedores.length > 0 ? (
            <PodioVendedores vendedores={dados.vendedores.vendedores.slice(0, VENDEDORES_NA_TV)} />
          ) : (
            <Vazio carregando={!dados} />
          )}
        </Quadro>
        <Quadro className="md:col-span-3 xl:col-span-2" titulo="Lojas" icone={Store}>
          {dados && dados.por_empresa.length > 0 ? (
            <ListaBarras
              itens={dados.por_empresa.map((e) => ({
                chave: e.empresa.codigo,
                rotulo: `${e.empresa.codigo} · ${nomeCurtoEmpresa(e.empresa.nome)}`,
                valor: paraNumero(e.faturamento),
                texto: formatarMoeda(e.faturamento),
              }))}
            />
          ) : (
            <Vazio carregando={!dados} />
          )}
        </Quadro>
        <Quadro className="md:col-span-3 xl:col-span-1" titulo="Canais" icone={Medal}>
          {dados && dados.por_canal.some((c) => paraNumero(c.faturamento) > 0) ? (
            <ListaBarras
              itens={dados.por_canal.map((c) => ({
                chave: c.canal,
                rotulo: CANAIS.find((x) => x.valor === c.canal)?.rotulo ?? c.rotulo,
                valor: paraNumero(c.faturamento),
                texto: formatarMoeda(c.faturamento),
              }))}
            />
          ) : (
            <Vazio carregando={!dados} />
          )}
        </Quadro>
      </main>
    </div>
  );
}


function descreverEscopo(descricaoPeriodo: string, resumo: ResumoVendas | null, codigoEmpresa: string, canal: string | null) {
  const empresa = resumo?.filtro.empresa;
  const nomeEmpresa = empresa ? nomeCurtoEmpresa(empresa.nome) : codigoEmpresa ? `Empresa ${codigoEmpresa}` : "consolidado";
  const nomeCanal = CANAIS.find((c) => c.valor === canal)?.rotulo.toLowerCase();
  return [descricaoPeriodo, nomeEmpresa, nomeCanal].filter(Boolean).join(" · ");
}

interface IndicadorProps {
  rotulo: string;
  icone: LucideIcon;
  valor: string | undefined;
  variacao?: { valor: Variacao; rotulo: string } | null;
  detalhe?: ReactNode;
  destaque?: boolean;
  className?: string;
}

function Indicador({ rotulo, icone: Icone, valor, variacao, detalhe, destaque = false, className = "" }: IndicadorProps) {
  return (
    <article
      className={`flex flex-col justify-between gap-[1vh] rounded-painel border-2 bg-superficie p-[2.5vh] ${destaque ? "border-acento" : "border-borda-forte"} ${className}`}
    >
      <h2 className="marca-apoio flex items-center gap-3 text-[clamp(0.9rem,2.2vh,1.6rem)] text-texto-2">
        <Icone aria-hidden className="size-[1.4em] shrink-0 text-acento" />
        {rotulo}
      </h2>
      <p
        className={`tabular font-display font-extrabold leading-none text-texto ${
          destaque ? "text-[clamp(2.75rem,10vh,8rem)]" : "text-[clamp(2rem,7vh,5rem)]"
        }`}
      >
        {valor ?? "—"}
      </p>
      <div className="flex flex-col gap-1 text-[clamp(0.9rem,2vh,1.4rem)]">
        {variacao && <IndicadorVariacao variacao={variacao.valor} rotulo={variacao.rotulo} />}
        {detalhe && <p className="text-texto-2">{detalhe}</p>}
      </div>
    </article>
  );
}

function Quadro({ titulo, icone: Icone, className = "", children }: { titulo: string; icone: LucideIcon; className?: string; children: ReactNode }) {
  return (
    <section aria-label={titulo} className={`flex flex-col gap-[1.5vh] rounded-painel border-2 border-borda-forte bg-superficie p-[2.5vh] ${className}`}>
      <h2 className="marca-apoio flex items-center gap-3 text-[clamp(0.9rem,2.2vh,1.6rem)] text-texto-2">
        <Icone aria-hidden className="size-[1.4em] shrink-0 text-acento" />
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function Vazio({ carregando }: { carregando: boolean }) {
  return <p className="text-[clamp(1rem,2.4vh,1.6rem)] text-texto-mudo">{carregando ? "Carregando…" : "Nenhuma venda no período"}</p>;
}


function PodioVendedores({ vendedores }: { vendedores: VendasPorVendedor[] }) {
  const maior = Math.max(...vendedores.map((v) => paraNumero(v.faturamento)), 0);
  return (
    <ol className="flex flex-col gap-[1.6vh]">
      {vendedores.map((v, i) => {
        const largura = maior > 0 ? (paraNumero(v.faturamento) / maior) * 100 : 0;
        return (
          <li key={v.id_vendedor} className="grid grid-cols-[2.2em_minmax(0,1fr)_auto] items-center gap-x-[1vw] gap-y-[0.6vh] text-[clamp(1rem,2.6vh,1.9rem)]">
            <span className={`tabular row-span-2 font-display font-extrabold ${i === 0 ? "text-acento" : "text-texto-mudo"}`}>{i + 1}º</span>
            <p className="min-w-0 truncate font-semibold">
              {v.nome ? nomeProprio(v.nome) : `Vendedor ${v.id_vendedor}`}
              <span className="tabular text-texto-mudo"> · {v.empresas.map((e) => e.codigo).join(" · ")}</span>
            </p>
            <p className="tabular text-right font-bold">{formatarMoeda(v.faturamento)}</p>
            <div className="col-span-2 h-[0.9vh] min-h-1.5 overflow-hidden rounded-sm bg-superficie-3" aria-hidden>
              <div className={`h-full rounded-sm ${i === 0 ? "bg-acento" : "bg-texto-2"}`} style={{ width: `${largura}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

interface ItemBarra {
  chave: string;
  rotulo: string;
  valor: number;
  texto: string;
}


function ListaBarras({ itens }: { itens: ItemBarra[] }) {
  const total = itens.reduce((soma, item) => soma + item.valor, 0);
  const maior = Math.max(...itens.map((item) => item.valor), 0);
  return (
    <ul className="flex flex-col gap-[1.6vh]">
      {itens.map((item) => (
        <li key={item.chave} className="flex flex-col gap-[0.6vh] text-[clamp(0.9rem,2.2vh,1.6rem)]">
          <div className="flex items-baseline justify-between gap-3">
            <p className="min-w-0 truncate font-semibold">{item.rotulo}</p>
            <p className="tabular shrink-0 text-texto-mudo">{formatarPercentual(participacao(item.valor, total))}</p>
          </div>
          <div className="h-[0.9vh] min-h-1.5 overflow-hidden rounded-sm bg-superficie-3" aria-hidden>
            <div className="h-full rounded-sm bg-texto-2" style={{ width: `${maior > 0 ? (item.valor / maior) * 100 : 0}%` }} />
          </div>
          <p className="tabular font-bold">{item.texto}</p>
        </li>
      ))}
    </ul>
  );
}
