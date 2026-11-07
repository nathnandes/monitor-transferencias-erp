import { Check, Clock, X, type LucideIcon } from "lucide-react";

import { formatarDataHora } from "../../../lib/format";
import type { EstadoEtapa, EtapaPipeline } from "../../../types/api";


const VISUAL: Record<EstadoEtapa, { icone: LucideIcon | null; circulo: string; texto: string; rotulo: string }> = {
  concluida: { icone: Check, circulo: "border-bom bg-bom text-white", texto: "text-texto", rotulo: "concluída" },
  atual: { icone: Clock, circulo: "border-aviso bg-aviso/20 text-aviso-texto animate-pulse", texto: "text-aviso-texto", rotulo: "em andamento" },
  falha: { icone: X, circulo: "border-critico bg-critico text-white", texto: "text-critico-texto", rotulo: "falhou" },
  pendente: { icone: null, circulo: "border-borda-forte bg-superficie-2 text-texto-mudo", texto: "text-texto-mudo", rotulo: "não iniciada" },
};


function corDaLigacao(estado: EstadoEtapa): string {
  return estado === "concluida" ? "bg-bom" : estado === "falha" ? "bg-critico" : "bg-borda-forte";
}


export function PipelineTransferencia({ etapas }: { etapas: EtapaPipeline[] }) {
  return (
    <ol aria-label="Etapas da transferência" className="flex flex-col gap-0 sm:flex-row sm:items-start">
      {etapas.map((etapa, i) => {
        const v = VISUAL[etapa.estado];
        const Icone = v.icone;
        const ultima = i === etapas.length - 1;
        return (
          <li
            key={etapa.chave}
            data-etapa={etapa.chave}
            data-estado={etapa.estado}
            aria-current={etapa.estado === "atual" ? "step" : undefined}
            className="relative flex flex-1 gap-3 pb-5 last:pb-0 sm:flex-col sm:items-center sm:gap-2 sm:pb-0 sm:text-center"
          >
            {!ultima && (
              <span
                aria-hidden
                className={`absolute left-[15px] top-8 h-[calc(100%-2rem)] w-0.5 sm:left-[calc(50%+1.25rem)] sm:top-[15px] sm:h-0.5 sm:w-[calc(100%-2.5rem)] ${corDaLigacao(etapa.estado)}`}
              />
            )}
            <span
              aria-hidden
              className={`relative z-10 grid size-8 shrink-0 place-items-center rounded-full border-2 ${v.circulo}`}
            >
              {Icone ? <Icone className="size-4" strokeWidth={3} /> : <span className="size-2 rounded-full bg-current" />}
            </span>
            <div className="min-w-0 sm:px-1">
              <p className={`text-sm font-semibold ${v.texto}`}>
                {etapa.rotulo}
                <span className="sr-only">: {v.rotulo}</span>
              </p>
              {etapa.momento && <p className="text-xs text-texto-mudo">{formatarDataHora(etapa.momento)}</p>}
              {etapa.detalhe && (
                <p
                  className={`text-xs ${etapa.estado === "falha" ? "font-semibold text-critico-texto" : "text-texto-2"} ${etapa.chave === "coi" && etapa.estado === "concluida" ? "font-mono" : ""}`}
                >
                  {etapa.detalhe}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
