import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

interface HeaderProps {
  titulo: string;

  subtitulo?: ReactNode;

  selo?: ReactNode;

  info?: ReactNode;

  aoAtualizar?: () => void;
  atualizando?: boolean;

  acoes?: ReactNode;

  filtros?: ReactNode;
}

export function Header({ titulo, subtitulo, selo, info, aoAtualizar, atualizando = false, acoes, filtros }: HeaderProps) {


  const aoClicar = () => {
    if (!atualizando) aoAtualizar?.();
  };

  return (
    <header className="relative z-30 border-b border-borda bg-superficie sm:sticky sm:top-0">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-4 px-4 py-4 sm:px-6 sm:py-5">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-texto sm:text-2xl sm:leading-tight">{titulo}</h1>
            {(subtitulo || selo) && (
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                {subtitulo && <p className="text-sm text-texto-mudo">{subtitulo}</p>}
                {selo}
              </div>
            )}
          </div>
          {(info || aoAtualizar || acoes) && (
            <div className="flex items-center gap-3 text-xs text-texto-mudo max-sm:w-full max-sm:flex-wrap max-sm:justify-end">
              {info && <div className="max-sm:w-full sm:text-right">{info}</div>}
              {acoes}
              {aoAtualizar && (
                <button
                  type="button"
                  onClick={aoClicar}
                  aria-busy={atualizando}
                  aria-disabled={atualizando || undefined}
                  className="btn btn-primario min-w-32 shrink-0"
                >
                  <RefreshCw aria-hidden className={`size-4 ${atualizando ? "animate-spin" : ""}`} />
                  {atualizando ? "Atualizando…" : "Atualizar"}
                </button>
              )}
            </div>
          )}
        </div>
        {filtros && <div className="border-t border-borda pt-4">{filtros}</div>}
      </div>
      {atualizando && (
        <div aria-hidden className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden">
          <div className="barra-progresso h-full w-2/5 bg-acento" />
        </div>
      )}
    </header>
  );
}
