import type { Tom } from "../../lib/status";
import type { Variacao } from "../../lib/variacao";


const CLASSE_TOM: Record<Tom, string> = {
  bom: "text-bom-texto",
  critico: "text-critico-texto",
  aviso: "text-aviso-texto",
  serio: "text-serio-texto",
  info: "text-info-texto",
  neutro: "text-texto-2",
};

interface IndicadorVariacaoProps {
  variacao: Variacao;

  rotulo: string;
  className?: string;
}


export function IndicadorVariacao({ variacao, rotulo, className = "" }: IndicadorVariacaoProps) {
  return (
    <span className={`flex flex-wrap items-baseline gap-x-1.5 ${className}`} title={variacao.descricao}>
      <span aria-hidden className={`tabular font-semibold ${CLASSE_TOM[variacao.tom]}`}>
        {variacao.texto}
      </span>
      <span aria-hidden className="text-texto-mudo">
        vs. {rotulo}
      </span>
      <span className="sr-only">{variacao.descricao}</span>
    </span>
  );
}
