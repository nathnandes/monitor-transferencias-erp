import { FlaskConical, Server } from "lucide-react";

import type { HealthLive } from "../../types/api";

export const TEXTO_SIMULADO = "Ambiente de desenvolvimento — dados simulados";


const NOME_AMBIENTE: Record<string, string> = { producao: "Produção", homologacao: "Homologação" };

interface EnvironmentBadgeProps {
  health: HealthLive | null;

  simulado: boolean;
}


export function EnvironmentBadge({ health, simulado }: EnvironmentBadgeProps) {
  if (simulado) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded border border-acento/50 bg-acento-suave px-2 py-0.5 text-xs font-semibold text-acento-texto">
        <FlaskConical aria-hidden className="size-3.5" />
        {TEXTO_SIMULADO}
      </span>
    );
  }

  const env = health?.env;
  const rotulo = !env
    ? "Ambiente: verificando..."
    : env === "development" || env === "test"
      ? "Ambiente de desenvolvimento"
      : `Ambiente: ${NOME_AMBIENTE[env] ?? env}`;

  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-borda bg-superficie-2 px-2 py-0.5 text-xs font-medium text-texto-2">
      <Server aria-hidden className="size-3.5" />
      {rotulo}
    </span>
  );
}
