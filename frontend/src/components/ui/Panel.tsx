import type { ReactNode } from "react";

interface PanelProps {
  titulo?: ReactNode;
  subtitulo?: ReactNode;

  acao?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;

  nivel?: 2 | 3;
}


export function Panel({ titulo, subtitulo, acao, children, className = "", id, nivel = 3 }: PanelProps) {
  const Titulo = nivel === 2 ? "h2" : "h3";
  return (
    <section
      id={id}
      className={`flex scroll-mt-28 flex-col rounded-painel border border-borda bg-superficie p-4 shadow-painel sm:p-painel ${className}`}
    >
      {(titulo || acao) && (
        <header className="mb-5 flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="min-w-0">
            {titulo && (
              <Titulo className="text-base font-bold tracking-tight text-texto">{titulo}</Titulo>
            )}
            {subtitulo && <p className="mt-1 text-xs text-texto-mudo">{subtitulo}</p>}
          </div>
          {acao && <div className="flex flex-wrap items-center gap-2">{acao}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
