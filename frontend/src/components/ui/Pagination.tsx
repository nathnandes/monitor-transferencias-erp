import { ChevronLeft, ChevronRight } from "lucide-react";

import { formatarNumero } from "../../lib/format";

interface PaginationProps {

  pagina: number;
  totalPaginas: number;
  totalRegistros: number;
  tamanhoPagina: number;

  itensNaPagina: number;
  aoMudarPagina: (pagina: number) => void;

  opcoesTamanho?: number[];
  aoMudarTamanho?: (tamanho: number) => void;
  desabilitado?: boolean;
}

const CLASSE_BOTAO = "btn btn-sm btn-secundario";

export function Pagination({
  pagina,
  totalPaginas,
  totalRegistros,
  tamanhoPagina,
  itensNaPagina,
  aoMudarPagina,
  opcoesTamanho,
  aoMudarTamanho,
  desabilitado = false,
}: PaginationProps) {
  const primeiro = itensNaPagina ? (pagina - 1) * tamanhoPagina + 1 : 0;
  const ultimo = itensNaPagina ? primeiro + itensNaPagina - 1 : 0;
  const paginas = Math.max(totalPaginas, 1);

  return (
    <nav aria-label="Paginação" className="flex flex-wrap items-center justify-between gap-3 text-xs text-texto-mudo">
      <p aria-live="polite">
        {itensNaPagina > 0 && (
          <>
            Exibindo {formatarNumero(primeiro)}–{formatarNumero(ultimo)} ·{" "}
          </>
        )}
        <strong className="font-medium text-texto-2">{formatarNumero(totalRegistros)}</strong>{" "}
        {totalRegistros === 1 ? "registro" : "registros"}
      </p>

      <div className="flex flex-wrap items-center gap-2 max-sm:w-full max-sm:justify-between">
        {opcoesTamanho && aoMudarTamanho && (
          <label className="flex items-center gap-1.5">
            Por página
            <select
              value={tamanhoPagina}
              onChange={(e) => aoMudarTamanho(Number(e.target.value))}
              disabled={desabilitado}
              className="campo h-9 w-auto px-2 sm:h-8"
            >
              {opcoesTamanho.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          onClick={() => aoMudarPagina(pagina - 1)}
          disabled={pagina <= 1 || desabilitado}
          className={CLASSE_BOTAO}
        >
          <ChevronLeft aria-hidden className="size-3.5" />
          Anterior
        </button>
        <span aria-current="page">
          Página <strong className="font-medium text-texto-2">{pagina}</strong> de {paginas}
        </span>
        <button
          type="button"
          onClick={() => aoMudarPagina(pagina + 1)}
          disabled={pagina >= totalPaginas || desabilitado}
          className={CLASSE_BOTAO}
        >
          Próxima
          <ChevronRight aria-hidden className="size-3.5" />
        </button>
      </div>
    </nav>
  );
}
