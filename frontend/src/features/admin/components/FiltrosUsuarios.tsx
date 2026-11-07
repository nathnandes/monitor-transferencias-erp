import { FunnelX, Search } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { FILTROS_USUARIOS_VAZIOS, type FiltrosUsuarios as Filtros } from "../../../types/admin";

interface FiltrosUsuariosProps {
  aplicados: Filtros;
  aoAplicar: (filtros: Filtros) => void;
  aoLimpar: () => void;
}

export function temFiltroUsuarios(f: Filtros): boolean {
  return Boolean(f.busca.trim() || f.role || f.ativo);
}


export function FiltrosUsuarios({ aplicados, aoAplicar, aoLimpar }: FiltrosUsuariosProps) {
  const [rascunho, setRascunho] = useState<Filtros>(aplicados);
  const idBusca = useId();
  const idRole = useId();
  const idStatus = useId();


  const [aplicadosVistos, setAplicadosVistos] = useState(aplicados);
  if (aplicados !== aplicadosVistos) {
    setAplicadosVistos(aplicados);
    setRascunho(aplicados);
  }

  const aoEnviar = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    aoAplicar({ ...rascunho, busca: rascunho.busca.trim() });
  };

  return (
    <form role="search" aria-label="Filtrar usuários" onSubmit={aoEnviar} className="flex flex-wrap items-end gap-3">
      <div className="flex min-w-56 flex-1 flex-col gap-1.5">
        <label htmlFor={idBusca} className="text-xs font-medium text-texto-2">
          Buscar por username ou nome
        </label>
        <input
          id={idBusca}
          type="search"
          maxLength={100}
          value={rascunho.busca}
          onChange={(e) => setRascunho((r) => ({ ...r, busca: e.target.value }))}
          className="campo"
        />
      </div>
      <div className="flex w-40 flex-col gap-1.5">
        <label htmlFor={idRole} className="text-xs font-medium text-texto-2">
          Papel
        </label>
        <select
          id={idRole}
          value={rascunho.role}
          onChange={(e) => setRascunho((r) => ({ ...r, role: e.target.value as Filtros["role"] }))}
          className="campo"
        >
          <option value="">Todos</option>
          <option value="ADMIN">ADMIN</option>
          <option value="OPERADOR">OPERADOR</option>
        </select>
      </div>
      <div className="flex w-40 flex-col gap-1.5">
        <label htmlFor={idStatus} className="text-xs font-medium text-texto-2">
          Status
        </label>
        <select
          id={idStatus}
          value={rascunho.ativo}
          onChange={(e) => setRascunho((r) => ({ ...r, ativo: e.target.value as Filtros["ativo"] }))}
          className="campo"
        >
          <option value="">Todos</option>
          <option value="true">Ativos</option>
          <option value="false">Inativos</option>
        </select>
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn btn-primario">
          <Search aria-hidden className="size-4" />
          Buscar
        </button>
        <button
          type="button"
          onClick={() => {
            setRascunho(FILTROS_USUARIOS_VAZIOS);
            aoLimpar();
          }}
          disabled={!temFiltroUsuarios(aplicados) && !temFiltroUsuarios(rascunho)}
          className="btn btn-secundario"
        >
          <FunnelX aria-hidden className="size-4" />
          Limpar
        </button>
      </div>
    </form>
  );
}
