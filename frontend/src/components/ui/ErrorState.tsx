import { FileWarning, RefreshCw, ServerCrash, TimerOff, TriangleAlert, WifiOff, type LucideIcon } from "lucide-react";

import { descreverErro, type CategoriaErro } from "../../lib/erros";

const ICONE: Record<CategoriaErro, LucideIcon> = {
  rede: WifiOff,
  timeout: TimerOff,
  api: ServerCrash,
  resposta: FileWarning,
  desconhecido: TriangleAlert,
};

interface ErrorStateProps {

  erro?: Error | null;

  mensagem?: string;
  titulo?: string;
  aoTentarNovamente?: () => void;
  className?: string;
}

export function ErrorState({ erro, mensagem, titulo = "Falha ao carregar", aoTentarNovamente, className = "" }: ErrorStateProps) {
  const descrito = erro ? descreverErro(erro) : null;
  const Icone = ICONE[descrito?.categoria ?? "desconhecido"];

  return (
    <div
      role="alert"
      className={`flex items-start gap-3 rounded-painel border border-critico/30 bg-critico/[0.05] px-4 py-4 ${className}`}
    >
      <Icone aria-hidden className="mt-0.5 size-4 shrink-0 text-critico-texto" />
      <div className="flex min-w-0 flex-1 flex-col items-start gap-1">
        <p className="flex flex-wrap items-baseline gap-x-2 text-sm font-semibold text-critico-texto">
          {titulo}
          {descrito && descrito.categoria !== "desconhecido" && (
            <span className="text-xs font-normal text-texto-mudo">{descrito.rotulo}</span>
          )}
        </p>
        <p className="max-w-prose text-sm text-texto-2">{mensagem ?? erro?.message}</p>
        {aoTentarNovamente && (
          <button type="button" onClick={aoTentarNovamente} className="btn btn-sm btn-secundario mt-2">
            <RefreshCw aria-hidden className="size-3.5" />
            Tentar novamente
          </button>
        )}
      </div>
    </div>
  );
}
