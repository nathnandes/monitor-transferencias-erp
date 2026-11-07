import { Funnel, FunnelX, X } from "lucide-react";
import { useId, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";

import { OCORRENCIAS, ROTULO_OCORRENCIA, ROTULO_SITUACAO_COI, SITUACOES_COI, rotuloDoStatus } from "../../../lib/status";
import { FILTROS_VAZIOS, type Empresa, type FiltrosTransferencia, type OcorrenciaControle, type SituacaoCoi } from "../../../types/api";
import { chaveDosFiltros, temFiltro } from "../lib/queryFilters";

interface FilterBarProps {
  empresas: Empresa[];
  carregandoEmpresas: boolean;

  opcoesStatus: string[];

  aplicados: FiltrosTransferencia;
  aoAplicar: (filtros: FiltrosTransferencia) => void;
  aoLimpar: () => void;
}

const ROTULO_CHIP: Record<keyof FiltrosTransferencia, string> = {
  empresa_origem: "Saiu de",
  empresa_destino: "Foi para",
  status: "Situação",
  situacao_coi: "COI",
  ocorrencia: "Problema",
  emitida_por: "Emitida por",
};

function Campo({ id, rotulo, children }: { id: string; rotulo: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-texto-2">
        {rotulo}
      </label>
      {children}
    </div>
  );
}


export function FilterBar({ empresas, carregandoEmpresas, opcoesStatus, aplicados, aoAplicar, aoLimpar }: FilterBarProps) {
  const [rascunho, setRascunho] = useState<FiltrosTransferencia>(aplicados);
  const idTitulo = useId();



  const [aplicadosVistos, setAplicadosVistos] = useState(aplicados);
  if (aplicados !== aplicadosVistos) {
    setAplicadosVistos(aplicados);
    setRascunho(aplicados);
  }

  const alterar =
    (campo: keyof FiltrosTransferencia) =>
    (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setRascunho((r) => ({ ...r, [campo]: e.target.value }));

  const pendente = chaveDosFiltros(rascunho) !== chaveDosFiltros(aplicados);
  const podeLimpar = temFiltro(aplicados) || temFiltro(rascunho);

  const ativos = (Object.keys(ROTULO_CHIP) as (keyof FiltrosTransferencia)[])
    .filter((campo) => aplicados[campo].trim() !== "")
    .map((campo) => {
      const valor = aplicados[campo];
      let texto = valor;
      if (campo === "empresa_origem" || campo === "empresa_destino") {
        const empresa = empresas.find((e) => e.codigo === valor);
        texto = empresa ? `${empresa.codigo} — ${empresa.nome}` : valor;
      }
      if (campo === "status") texto = rotuloDoStatus(valor);
      if (campo === "situacao_coi") texto = ROTULO_SITUACAO_COI[valor as SituacaoCoi] ?? valor;
      if (campo === "ocorrencia") texto = ROTULO_OCORRENCIA[valor as OcorrenciaControle] ?? valor;
      return { campo, texto: `${ROTULO_CHIP[campo]}: ${texto}` };
    });

  const aoEnviar = (e: FormEvent) => {
    e.preventDefault();
    aoAplicar(rascunho);
  };

  const opcoesEmpresa = (
    <>
      <option value="">{carregandoEmpresas ? "Carregando..." : "Todas"}</option>
      {empresas.map((e) => (
        <option key={e.id} value={e.codigo}>
          {e.codigo} — {e.nome}
          {e.ativo ? "" : " (inativa)"}
        </option>
      ))}
    </>
  );

  return (
    <form
      role="search"
      aria-labelledby={idTitulo}
      onSubmit={aoEnviar}
      noValidate
      className="rounded-painel border border-borda bg-superficie p-4 shadow-painel sm:p-painel"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 id={idTitulo} className="flex items-center gap-2 text-[15px] font-semibold text-texto">
          <Funnel aria-hidden className="size-4 text-texto-mudo" />
          Filtrar a lista
        </h3>
        <p className="text-xs text-texto-mudo">A loja e o período do topo da página continuam valendo.</p>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        <Campo id="f-origem" rotulo="Saiu de">
          <select id="f-origem" className="campo" value={rascunho.empresa_origem} onChange={alterar("empresa_origem")} disabled={carregandoEmpresas}>
            {opcoesEmpresa}
          </select>
        </Campo>
        <Campo id="f-destino" rotulo="Foi para">
          <select id="f-destino" className="campo" value={rascunho.empresa_destino} onChange={alterar("empresa_destino")} disabled={carregandoEmpresas}>
            {opcoesEmpresa}
          </select>
        </Campo>
        <Campo id="f-status" rotulo="Situação">
          <select id="f-status" className="campo" value={rascunho.status} onChange={alterar("status")}>
            <option value="">Todas</option>
            {opcoesStatus.map((s) => (
              <option key={s} value={s}>
                {rotuloDoStatus(s)}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="f-ocorrencia" rotulo="Problema">
          <select id="f-ocorrencia" className="campo" value={rascunho.ocorrencia} onChange={alterar("ocorrencia")}>
            <option value="">Qualquer um</option>
            {OCORRENCIAS.map((o) => (
              <option key={o} value={o}>
                {ROTULO_OCORRENCIA[o]}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="f-coi" rotulo="COI">
          <select id="f-coi" className="campo" value={rascunho.situacao_coi} onChange={alterar("situacao_coi")}>
            <option value="">Todos</option>
            {SITUACOES_COI.map((s) => (
              <option key={s} value={s}>
                {ROTULO_SITUACAO_COI[s]}
              </option>
            ))}
          </select>
        </Campo>
        <Campo id="f-emitida-por" rotulo="Emitida por">
          <input
            id="f-emitida-por"
            className="campo"
            value={rascunho.emitida_por}
            onChange={alterar("emitida_por")}
            placeholder="Usuário do ERP"
            autoComplete="off"
          />
        </Campo>
      </div>

      {ativos.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-texto-mudo">Aplicados:</span>
          <ul aria-label="Filtros aplicados" className="flex flex-wrap gap-2">
            {ativos.map(({ campo, texto }) => (
              <li
                key={campo}
                className="inline-flex items-center gap-1 rounded border border-borda-forte bg-superficie-2 py-0.5 pl-2.5 pr-0.5 text-xs font-medium text-texto"
              >
                {texto}
                <button
                  type="button"
                  aria-label={`Remover filtro ${texto}`}
                  onClick={() => aoAplicar({ ...aplicados, [campo]: "" })}
                  className="grid size-6 place-items-center rounded-sm text-texto-mudo hover:bg-superficie-3 hover:text-texto"
                >
                  <X aria-hidden className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3 border-t border-borda pt-4 sm:flex-row sm:items-center sm:justify-end">
        {pendente && (
          <p className="flex items-center gap-1.5 text-xs font-medium text-aviso-texto sm:mr-auto">
            <span aria-hidden className="size-1.5 rounded-full bg-aviso" />
            Há alterações não aplicadas.
          </p>
        )}
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <button
            type="button"
            onClick={() => {
              setRascunho(FILTROS_VAZIOS);
              aoLimpar();
            }}
            disabled={!podeLimpar}
            className={`btn ${podeLimpar ? "btn-acento-suave" : "btn-secundario"}`}
          >
            <FunnelX aria-hidden className="size-4" />
            Limpar filtros
          </button>
          <button type="submit" className="btn btn-primario">
            <Funnel aria-hidden className="size-4" />
            Aplicar filtros
          </button>
        </div>
      </div>
    </form>
  );
}
