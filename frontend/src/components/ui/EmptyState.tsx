import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  titulo: string;
  descricao?: string;
  icone?: LucideIcon;

  acao?: ReactNode;
  className?: string;
}

export function EmptyState({ titulo, descricao, icone: Icone = Inbox, acao, className = "" }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center gap-1 px-4 py-10 text-center ${className}`}>
      <Icone aria-hidden className="mb-2 size-6 text-texto-mudo/70" strokeWidth={1.5} />
      <p className="text-sm font-semibold text-texto-2">{titulo}</p>
      {descricao && <p className="max-w-sm text-xs text-texto-mudo">{descricao}</p>}
      {acao && <div className="mt-3">{acao}</div>}
    </div>
  );
}
