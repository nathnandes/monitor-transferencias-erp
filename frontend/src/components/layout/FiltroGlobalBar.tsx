import { Building2, CalendarDays, Check } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { EstadoFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { validarIntervalo } from "../../lib/datas";
import { nomeCurtoEmpresa, rotuloDiaCurto } from "../../lib/format";
import { PERIODOS, type Periodo } from "../../lib/periodo";
import type { EmpresaResumo } from "../../types/api";

interface FiltroGlobalBarProps {
  estado: EstadoFiltroGlobal;

  empresas: EmpresaResumo[] | null;
  carregandoEmpresas?: boolean;

  semConsolidado?: boolean;
}


export function FiltroGlobalBar({ estado, empresas, carregandoEmpresas = false, semConsolidado = false }: FiltroGlobalBarProps) {
  const { filtro, comparacao, intervalo, definir } = estado;
  const [inicio, setInicio] = useState(filtro.dataInicial);
  const [fim, setFim] = useState(filtro.dataFinal);

  const [editandoPersonalizado, setEditandoPersonalizado] = useState(false);



  const aplicadas = `${filtro.dataInicial}|${filtro.dataFinal}`;
  const [aplicadasVistas, setAplicadasVistas] = useState(aplicadas);
  if (aplicadas !== aplicadasVistas) {
    setAplicadasVistas(aplicadas);
    setInicio(filtro.dataInicial);
    setFim(filtro.dataFinal);
  }

  const personalizadoAberto = editandoPersonalizado || filtro.periodo === "personalizado";
  const erroDatas = inicio && fim ? validarIntervalo(inicio, fim) : null;

  const escolherPeriodo = (periodo: Periodo) => {
    if (periodo === "personalizado") {
      setEditandoPersonalizado(true);
      return;
    }
    setEditandoPersonalizado(false);
    definir({ ...filtro, periodo, dataInicial: "", dataFinal: "" });
  };

  const aplicarPersonalizado = (e: FormEvent) => {
    e.preventDefault();
    if (!inicio || !fim || erroDatas) return;
    setEditandoPersonalizado(false);
    definir({ ...filtro, periodo: "personalizado", dataInicial: inicio, dataFinal: fim });
  };

  const lista = empresas ?? [];

  const empresaForaDaLista = filtro.empresa && !lista.some((e) => e.codigo === filtro.empresa);

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5" role="group" aria-label="Filtro global">
      <label className="flex min-w-0 max-w-full items-center gap-2 text-xs font-medium text-texto-2">
        <Building2 aria-hidden className="size-4 text-texto-mudo" />
        <span className="sr-only sm:not-sr-only">Empresa</span>
        <select
          className="campo h-9 w-auto min-w-44 max-w-full sm:h-8"
          value={filtro.empresa}
          disabled={carregandoEmpresas}
          onChange={(e) => definir({ ...filtro, empresa: e.target.value })}
        >
          {!semConsolidado && <option value="">{carregandoEmpresas ? "Carregando…" : "Consolidado (todas)"}</option>}
          {empresaForaDaLista && <option value={filtro.empresa}>Empresa {filtro.empresa}</option>}
          {lista.map((e) => (
            <option key={e.codigo} value={e.codigo}>
              {e.codigo} — {nomeCurtoEmpresa(e.nome)}
            </option>
          ))}
        </select>
      </label>

      <div className="flex items-center gap-2">
        <CalendarDays aria-hidden className="size-4 text-texto-mudo" />
        <div role="group" aria-label="Período" className="flex flex-wrap rounded-lg border border-borda bg-superficie-2 p-0.5">
          {PERIODOS.map(({ valor, rotulo }) => {
            const ativo = valor === "personalizado" ? personalizadoAberto : !personalizadoAberto && filtro.periodo === valor;
            return (
              <button
                key={valor}
                type="button"
                aria-pressed={ativo}
                onClick={() => escolherPeriodo(valor)}
                className={`h-8 rounded-md px-3 text-xs font-semibold transition-colors sm:h-7 ${
                  ativo ? "bg-texto text-superficie shadow-sm" : "text-texto-2 hover:bg-superficie-3 hover:text-texto"
                }`}
              >
                {rotulo}
              </button>
            );
          })}
        </div>
      </div>

      {personalizadoAberto && (
        <form onSubmit={aplicarPersonalizado} className="flex flex-wrap items-center gap-2" noValidate>
          <label className="flex items-center gap-1.5 text-xs text-texto-2">
            De
            <input
              type="date"
              className="campo h-9 w-auto sm:h-8"
              value={inicio}
              max={fim || undefined}
              onChange={(e) => setInicio(e.target.value)}
              aria-invalid={Boolean(erroDatas)}
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-texto-2">
            Até
            <input
              type="date"
              className="campo h-9 w-auto sm:h-8"
              value={fim}
              min={inicio || undefined}
              onChange={(e) => setFim(e.target.value)}
              aria-invalid={Boolean(erroDatas)}
            />
          </label>
          <button type="submit" className="btn btn-sm btn-primario" disabled={!inicio || !fim || Boolean(erroDatas)}>
            <Check aria-hidden className="size-3.5" />
            Aplicar
          </button>
          {erroDatas && (
            <span role="alert" className="text-xs font-medium text-critico-texto">
              {erroDatas}
            </span>
          )}
        </form>
      )}

      {comparacao && intervalo && !editandoPersonalizado && (
        <p className="text-xs text-texto-mudo">
          Comparando com {comparacao.rotulo}
          {comparacao.inicio === comparacao.fim
            ? ` (${rotuloDiaCurto(comparacao.inicio)})`
            : ` (${rotuloDiaCurto(comparacao.inicio)} a ${rotuloDiaCurto(comparacao.fim)})`}
        </p>
      )}
    </div>
  );
}
