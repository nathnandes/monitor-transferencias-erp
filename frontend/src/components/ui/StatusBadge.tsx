import type { ReactNode } from "react";

import type { Tom } from "../../lib/status";

const CLASSES_TOM: Record<Tom, string> = {
  bom: "bg-bom/10 text-bom-texto",
  aviso: "bg-aviso/12 text-aviso-texto",
  serio: "bg-serio/12 text-serio-texto",
  critico: "bg-critico/10 text-critico-texto",
  info: "bg-info/10 text-info-texto",
  neutro: "bg-texto/6 text-texto-2",
};

interface StatusBadgeProps {
  tom: Tom;
  children: ReactNode;
  className?: string;
}


export function StatusBadge({ tom, children, className = "" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ${CLASSES_TOM[tom]} ${className}`}
    >
      <span aria-hidden className="size-1.5 rounded-[1px] bg-current" />
      {children}
    </span>
  );
}
