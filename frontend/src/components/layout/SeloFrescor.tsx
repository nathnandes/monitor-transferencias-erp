import { DatabaseZap } from "lucide-react";

import { useAsync } from "../../hooks/useAsync";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { formatarDataHora, tempoRelativo } from "../../lib/format";
import { getFrescor } from "../../services/frescorService";
import type { FrescorTipo, SituacaoFrescor, TipoFrescor } from "../../types/api";

const ROTULO: Record<TipoFrescor, string> = {
  transferencias: "transferências",
  estoque: "estoque",
  precos: "preços",
  vendas: "vendas",
  movimentos_estoque: "movimentos de estoque",
};

const GRAVIDADE: Record<SituacaoFrescor, number> = { EM_DIA: 0, NUNCA: 1, ATRASADA: 2, PARADA: 3 };

const TOM: Record<SituacaoFrescor, string> = {
  EM_DIA: "text-texto-mudo",
  NUNCA: "text-texto-mudo",
  ATRASADA: "font-semibold text-aviso-texto",
  PARADA: "font-semibold text-critico-texto",
};


export function pior(fontes: FrescorTipo[]): FrescorTipo | null {
  return fontes.reduce<FrescorTipo | null>((acc, f) => {
    if (!acc) return f;
    if (GRAVIDADE[f.situacao] !== GRAVIDADE[acc.situacao]) return GRAVIDADE[f.situacao] > GRAVIDADE[acc.situacao] ? f : acc;
    return (f.ultima_conclusao ?? "") < (acc.ultima_conclusao ?? "") ? f : acc;
  }, null);
}

function texto(f: FrescorTipo): string {
  if (f.situacao === "NUNCA") return `ERP: ${ROTULO[f.tipo]} ainda não sincronizado`;
  const quando = tempoRelativo(f.ultima_conclusao);
  if (f.situacao === "EM_DIA") return `Dados do ERP ${quando}`;
  return `Sincronização de ${ROTULO[f.tipo]} ${f.situacao === "PARADA" ? "parada" : "atrasada"}: dados ${quando}`;
}


export function SeloFrescor({ fontes }: { fontes: TipoFrescor[] }) {
  const consulta = useAsync((s) => getFrescor(s), []);
  useAtualizacaoAutomatica(consulta.recarregar);

  const frescor = consulta.data;
  if (!frescor) return null;
  const f = pior(frescor.tipos.filter((t) => fontes.includes(t.tipo)));
  if (!f) return null;

  const detalhe = frescor.tipos
    .filter((t) => fontes.includes(t.tipo))
    .map((t) => `${ROTULO[t.tipo]}: ${t.ultima_conclusao ? formatarDataHora(t.ultima_conclusao) : "nunca"}`)
    .join(" · ");
  return (
    <p className={`mt-0.5 flex items-center gap-1 text-[11px] ${TOM[f.situacao]}`} title={`Última sincronização — ${detalhe}`}>
      <DatabaseZap aria-hidden className="size-3 shrink-0" />
      {texto(f)}
    </p>
  );
}
