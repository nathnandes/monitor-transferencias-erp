import { Clock } from "lucide-react";

import { formatarDataHora, formatarHora } from "../../lib/format";
import type { TipoFrescor } from "../../types/api";
import { SeloFrescor } from "./SeloFrescor";

interface IndicadorAtualizacaoProps {
  atualizadoEm: Date | null;

  geradoEm?: string | null;
  atualizando: boolean;

  fontes?: TipoFrescor[];
}


export function IndicadorAtualizacao({ atualizadoEm, geradoEm = null, atualizando, fontes }: IndicadorAtualizacaoProps) {
  return (
    <div aria-live="polite" className="flex items-start gap-2 leading-tight">
      <Clock aria-hidden className="mt-px size-3.5 shrink-0 text-texto-mudo" />
      <div>
        <p className="text-texto-2">
          {atualizando && !atualizadoEm
            ? "Carregando..."
            : atualizadoEm
              ? `Atualizado às ${formatarHora(atualizadoEm)}`
              : "Ainda não atualizado"}
          {atualizando && atualizadoEm && " · atualizando..."}
        </p>
        {geradoEm && <p className="mt-0.5 text-[11px]">Resumo gerado em {formatarDataHora(geradoEm)}</p>}
        {fontes && fontes.length > 0 && <SeloFrescor fontes={fontes} />}
      </div>
    </div>
  );
}
