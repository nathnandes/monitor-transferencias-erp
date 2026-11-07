import { ArrowDownToLine, ArrowUpFromLine, Building2 } from "lucide-react";
import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis } from "recharts";

import { Dica } from "../../../components/ui/Dica";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { SEM_VALOR } from "../../../components/ui/MetricCard";
import { formatarNumero, nomeCurtoEmpresa } from "../../../lib/format";
import { COR_TOM, ROTULO_EMPRESA, tomDaEmpresa } from "../../../lib/status";
import type { GranularidadeIndicadores, IndicadoresEmpresa, IndicadoresPorEmpresa, StatusEmpresa } from "../../../types/api";
import { INDICADORES, pontosDoCard, semMovimento, type DefinicaoIndicador, type PontoCard } from "../lib/indicadoresEmpresa";
import { COR_EIXO, COR_GRADE, COR_TICK, COR_TICK_FORTE, CURSOR_BARRA } from "../../../components/charts/chartTheme";

const ALTURA_GRAFICO = 130;

interface IndicadoresEmpresasProps {
  dados: IndicadoresPorEmpresa | null;
  carregando: boolean;
  erro: Error | null;
  aoTentarNovamente: () => void;

  situacoes?: StatusEmpresa[];
}


export function IndicadoresEmpresas({ dados, carregando, erro, aoTentarNovamente, situacoes = [] }: IndicadoresEmpresasProps) {
  const [escolhida, setEscolhida] = useState<string | null>(null);
  if (erro && !dados) {
    return <ErrorState titulo="Não foi possível carregar os indicadores por empresa" erro={erro} aoTentarNovamente={aoTentarNovamente} />;
  }
  if (!dados) return <LoadingState rotulo="Carregando indicadores por empresa..." altura={ALTURA_GRAFICO * 2} />;
  if (dados.empresas.length === 0) {
    return (
      <div className="rounded-painel border border-borda bg-superficie">
        <EmptyState icone={Building2} titulo="Nenhuma empresa ativa" descricao="Cadastre ou ative empresas para ver os indicadores." />
      </div>
    );
  }


  const atual = dados.empresas.find((e) => e.empresa.codigo === escolhida) ?? dados.empresas[0]!;

  return (
    <div aria-busy={carregando} className={`flex flex-col gap-3 transition-opacity ${carregando ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {dados.empresas.length > 1 ? (
          <div role="group" aria-label="Empresa dos indicadores" className="flex flex-wrap gap-1.5">
            {dados.empresas.map(({ empresa, totais }) => {
              const ativa = empresa.codigo === atual.empresa.codigo;
              const situacao = situacoes.find((x) => x.empresa.codigo === empresa.codigo);
              const tom = situacao ? tomDaEmpresa(situacao.status) : null;
              return (
                <button
                  key={empresa.id}
                  type="button"
                  aria-pressed={ativa}
                  onClick={() => setEscolhida(empresa.codigo)}
                  title={`${empresa.nome}${situacao ? ` · ${ROTULO_EMPRESA[situacao.status]}` : ""} · ${totais.a_receber} a receber`}
                  className={`flex h-9 items-center gap-2 rounded-md border px-3 text-sm font-medium transition-colors active:translate-y-px ${
                    ativa
                      ? "border-texto bg-texto text-superficie shadow-painel"
                      : "border-borda bg-superficie text-texto-2 hover:border-borda-forte hover:text-texto"
                  }`}
                >
                  {tom && (
                    <span
                      role="img"
                      aria-label={ROTULO_EMPRESA[situacao!.status]}
                      className="size-2 shrink-0 rounded-full"
                      style={{ background: COR_TOM[tom] }}
                    />
                  )}
                  <span className={`tabular font-semibold ${ativa ? "" : "text-texto-mudo"}`}>{empresa.codigo}</span>
                  {nomeCurtoEmpresa(empresa.nome)}
                  {totais.a_receber > 0 && (
                    <span
                      className={`tabular rounded px-1 text-[11px] font-semibold ${
                        ativa ? "bg-superficie/20" : "bg-aviso/15 text-aviso-texto"
                      }`}
                    >
                      {formatarNumero(totais.a_receber)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ) : null}
        <p className="ml-auto flex items-center gap-3 text-xs text-texto-mudo">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block size-2 rounded-sm bg-texto-2" /> Coluna = resultado
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-0 w-4 border-t-2 border-dashed border-texto-2" /> Linha = média do período
          </span>
        </p>
      </div>
      <BlocoEmpresa key={atual.empresa.id} item={atual} granularidade={dados.granularidade} />
    </div>
  );
}


const GRUPOS = [
  { titulo: "Como destino", descricao: "o que a loja recebe", icone: ArrowDownToLine, defs: INDICADORES.slice(0, 4) },
  { titulo: "Como origem", descricao: "o que a loja envia", icone: ArrowUpFromLine, defs: INDICADORES.slice(4) },
];

function BlocoEmpresa({ item, granularidade }: { item: IndicadoresEmpresa; granularidade: GranularidadeIndicadores }) {
  const { empresa } = item;
  const idTitulo = `empresa-${empresa.codigo}`;
  return (
    <section
      aria-labelledby={idTitulo}
      className="overflow-hidden rounded-painel border border-borda-forte bg-superficie shadow-elevado"
    >
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-borda border-t-4 border-t-acento bg-superficie-2 px-4 py-3 sm:px-painel">
        <h3 id={idTitulo} className="flex items-baseline gap-2 font-display text-xl font-extrabold tracking-tight text-texto">
          <span className="tabular text-texto-mudo">{empresa.codigo}</span>
          {nomeCurtoEmpresa(empresa.nome)}
        </h3>
        {nomeCurtoEmpresa(empresa.nome) !== empresa.nome && <p className="text-xs text-texto-mudo">{empresa.nome}</p>}
      </header>
      <div className="p-4 sm:p-painel">
        {semMovimento(item.totais) ? (
          <p className="rounded-lg border border-dashed border-borda px-4 py-6 text-center text-sm text-texto-mudo">
            Nenhuma transferência enviada, recebida ou a receber no período.
          </p>
        ) : (
          <div className="flex flex-col gap-5">
            {GRUPOS.map(({ titulo, descricao, icone: Icone, defs }) => (
              <div key={titulo}>
                <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-texto-2">
                  <Icone aria-hidden className="size-3.5 text-texto-mudo" />
                  {titulo}
                  <span className="font-normal text-texto-mudo">· {descricao}</span>
                </h4>
                <div className="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
                  {defs.map((def) => (
                    <CardIndicador
                      key={def.campo}
                      def={def}
                      total={item.totais[def.campo]}
                      pontos={pontosDoCard(item.serie, def.campo, granularidade)}
                      empresa={empresa.codigo}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

interface CardIndicadorProps {
  def: DefinicaoIndicador;
  total: number | null;
  pontos: PontoCard[];
  empresa: string;
}

function CardIndicador({ def, total, pontos, empresa }: CardIndicadorProps) {
  const valorTotal = total === null ? SEM_VALOR : def.formatar(total);
  const descricao = pontos
    .filter((p) => p.valor !== null)
    .map((p) => `${p.rotuloCompleto}: ${def.formatar(p.valor!)}`)
    .join(", ");

  return (
    <article
      className="flex flex-col rounded-lg border border-borda border-t-[3px] bg-superficie p-3 transition-colors hover:border-borda-forte"
      style={{ borderTopColor: def.cor }}
    >
      <header className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h5 className="text-[11px] font-semibold uppercase leading-tight tracking-wide text-texto-mudo">{def.titulo}</h5>
          <p className="tabular mt-1.5 font-display text-2xl font-extrabold leading-none text-texto">{valorTotal}</p>
        </div>
        <Dica texto={def.dica} sobre={def.titulo} />
      </header>
      <figure aria-label={`${def.titulo} da empresa ${empresa}`}>
        <figcaption className="sr-only">{descricao || "Sem valores no período."}</figcaption>
        <ResponsiveContainer width="100%" height={ALTURA_GRAFICO}>
          <ComposedChart data={pontos} margin={{ top: 6, right: 2, bottom: 0, left: 2 }}>
            <CartesianGrid vertical={false} stroke={COR_GRADE} />
            <XAxis
              dataKey="rotulo"
              tick={{ fill: COR_TICK, fontSize: 10 }}
              axisLine={{ stroke: COR_EIXO }}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={8}
            />
            <Tooltip cursor={CURSOR_BARRA} content={<ConteudoTooltip def={def} />} />
            <Bar
              dataKey="valor"
              name={def.titulo}
              fill={def.cor}
              fillOpacity={0.85}
              radius={[3, 3, 0, 0]}
              maxBarSize={28}
              isAnimationActive={false}
            />
            <Line
              dataKey="media"
              name="Média do período"
              stroke={COR_TICK_FORTE}
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </figure>
    </article>
  );
}

interface PropsTooltip {
  def: DefinicaoIndicador;
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: unknown }>;
}

function ConteudoTooltip({ def, active, payload }: PropsTooltip) {
  const ponto = payload?.[0]?.payload as PontoCard | undefined;
  if (!active || !ponto) return null;
  return (
    <div className="rounded-md border border-borda-forte bg-superficie px-3 py-2 text-xs shadow-elevado">
      <p className="mb-1 font-medium text-texto">{ponto.rotuloCompleto}</p>
      <p className="flex items-center gap-2 text-texto-2">
        <span aria-hidden className="size-2 rounded-sm" style={{ background: def.cor }} />
        {def.titulo}
        <span className="tabular ml-auto pl-3 font-medium text-texto">{ponto.valor === null ? SEM_VALOR : def.formatar(ponto.valor)}</span>
      </p>
      {ponto.media !== null && (
        <p className="flex items-center gap-2 text-texto-mudo">
          <span aria-hidden className="h-0 w-2 border-t-2 border-dashed border-texto-2" />
          Média do período
          <span className="tabular ml-auto pl-3">{def.formatar(ponto.media)}</span>
        </p>
      )}
    </div>
  );
}
