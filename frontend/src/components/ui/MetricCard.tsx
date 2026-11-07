import { ArrowUpRight, type LucideIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router";

import type { Tom } from "../../lib/status";
import type { Variacao } from "../../lib/variacao";
import { Dica } from "./Dica";
import { IndicadorVariacao } from "./IndicadorVariacao";


const CLASSE_ICONE: Record<Tom, string> = {
  bom: "text-bom-texto",
  aviso: "text-aviso-texto",
  serio: "text-serio-texto",
  critico: "text-critico-texto",
  info: "text-info-texto",
  neutro: "text-texto-mudo",
};


export const SEM_VALOR = "—";

interface MetricCardProps {
  rotulo: string;

  valor?: ReactNode;
  detalhe?: ReactNode;
  tom?: Tom;

  destaque?: boolean;
  icone?: LucideIcon;

  dica?: string;
  carregando?: boolean;

  variacao?: { valor: Variacao; rotulo: string } | null;

  para?: string;
}


function tamanhoDoValor(valor: ReactNode): CSSProperties | undefined {
  if (typeof valor !== "string" || valor.length <= 8) return undefined;
  return { fontSize: `min(2rem, ${(165 / valor.length).toFixed(1)}cqi)` };
}


export function MetricCard({
  rotulo,
  valor,
  detalhe,
  tom = "neutro",
  destaque = false,
  icone: Icone,
  dica,
  carregando = false,
  variacao,
  para,
}: MetricCardProps) {
  return (
    <article
      aria-busy={carregando}
      className={`@container relative flex flex-col overflow-hidden rounded-painel border border-borda bg-superficie px-5 pt-4 pb-5 shadow-painel ${destaque ? "shadow-[inset_0_2px_0_var(--color-acento)]" : ""} ${para ? "group transition-colors hover:border-borda-forte hover:bg-superficie-2 focus-within:ring-2 focus-within:ring-acento" : ""}`}
    >
      <div className="flex items-center gap-2">
        {Icone && <Icone aria-hidden strokeWidth={1.75} className={`size-4 shrink-0 ${destaque ? "text-texto" : CLASSE_ICONE[tom]}`} />}
        <h3 className="min-w-0 flex-1 text-[13px] font-medium leading-tight text-texto-2">
          {para ? (

            <Link to={para} className="outline-none after:absolute after:inset-0 after:content-[''] group-hover:text-texto">
              {rotulo}
            </Link>
          ) : (
            rotulo
          )}
        </h3>
        {dica && (
          <span className="relative z-10">
            <Dica sobre={rotulo} texto={dica} />
          </span>
        )}
        {para && <ArrowUpRight aria-hidden className="size-3.5 shrink-0 text-texto-mudo group-hover:text-texto" />}
      </div>
      {carregando ? (
        <>
          <p className="tabular mt-4 animate-pulse font-display text-metrica text-texto-mudo">{SEM_VALOR}</p>
          <p className="mt-1 text-xs text-texto-mudo">Carregando...</p>
        </>
      ) : (
        <>
          <p className="tabular mt-4 whitespace-nowrap font-display text-metrica tracking-tight text-texto" style={tamanhoDoValor(valor)}>
            {valor ?? SEM_VALOR}
          </p>
          {variacao && <IndicadorVariacao variacao={variacao.valor} rotulo={variacao.rotulo} className="mt-1.5 text-xs" />}
          {detalhe && <div className="mt-1.5 text-xs text-texto-2">{detalhe}</div>}
        </>
      )}
    </article>
  );
}
