import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface SectionHeaderProps {
  id: string;
  titulo: string;
  descricao?: ReactNode;
  icone?: LucideIcon;
}


export function SectionHeader({ id, titulo, descricao, icone: Icone }: SectionHeaderProps) {
  return (
    <header className="mb-4 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-borda pb-2.5">
      <h2 id={id} className="flex items-center gap-2 text-base font-bold text-texto sm:text-lg">
        {Icone && <Icone aria-hidden strokeWidth={1.75} className="size-[1.1em] text-texto-mudo" />}
        {titulo}
      </h2>
      {descricao && <p className="text-[13px] text-texto-mudo">{descricao}</p>}
    </header>
  );
}
