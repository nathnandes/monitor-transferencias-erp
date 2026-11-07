import { KeyRound, Pencil, UserCheck, UserX } from "lucide-react";

import { StatusBadge } from "../../../components/ui/StatusBadge";
import { formatarDataHora } from "../../../lib/format";
import type { UsuarioAdmin } from "../../../types/admin";

export const MOTIVO_PROPRIO = "Não vale para a sua própria conta: peça a outro ADMIN.";

interface UsuariosTabelaProps {
  itens: UsuarioAdmin[];
  idProprio: number;

  ocupadoId: number | null;
  aoEditar: (usuario: UsuarioAdmin) => void;
  aoRedefinirSenha: (usuario: UsuarioAdmin) => void;
  aoAtivar: (usuario: UsuarioAdmin) => void;
  aoDesativar: (usuario: UsuarioAdmin) => void;
}

const TH = "px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-texto-mudo";
const TD = "px-3 py-2.5 align-middle";


export function UsuariosTabela({
  itens,
  idProprio,
  ocupadoId,
  aoEditar,
  aoRedefinirSenha,
  aoAtivar,
  aoDesativar,
}: UsuariosTabelaProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] border-collapse text-sm">
        <caption className="sr-only">Usuários locais</caption>
        <thead className="bg-superficie-2">
          <tr>
            <th scope="col" className={TH}>Username</th>
            <th scope="col" className={TH}>Nome</th>
            <th scope="col" className={TH}>Papel</th>
            <th scope="col" className={TH}>Perfil de acesso</th>
            <th scope="col" className={TH}>Status</th>
            <th scope="col" className={TH}>Criado em</th>
            <th scope="col" className={TH}>Último login</th>
            <th scope="col" className={`${TH} text-right`}>Ações</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((u) => {
            const proprio = u.id === idProprio;
            const ocupado = ocupadoId === u.id;
            return (
              <tr key={u.id} className="border-t border-borda hover:bg-superficie-2/40">
                <td className={`${TD} whitespace-nowrap font-mono text-texto`}>
                  {u.username}
                  {proprio && <span className="ml-1.5 font-sans text-xs text-acento-texto">(você)</span>}
                </td>
                <td className={`${TD} whitespace-nowrap text-texto-2`}>{u.nome_exibicao}</td>
                <td className={TD}>
                  <StatusBadge tom={u.role === "ADMIN" ? "info" : "neutro"}>{u.role}</StatusBadge>
                </td>
                <td className={`${TD} whitespace-nowrap text-texto-2`}>
                  {u.perfil ? u.perfil.nome : <span className="text-texto-mudo">Sem perfil</span>}
                </td>
                <td className={TD}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <StatusBadge tom={u.ativo ? "bom" : "critico"}>{u.ativo ? "Ativo" : "Inativo"}</StatusBadge>
                    {u.must_change_password && <StatusBadge tom="aviso">Troca de senha pendente</StatusBadge>}
                    {u.sessao_continua && <StatusBadge tom="info">Modo TV</StatusBadge>}
                  </div>
                </td>
                <td className={`${TD} tabular whitespace-nowrap text-texto-2`}>{formatarDataHora(u.created_at)}</td>
                <td className={`${TD} tabular whitespace-nowrap text-texto-2`}>{u.last_login_at ? formatarDataHora(u.last_login_at) : "Nunca"}</td>
                <td className={`${TD} text-right`}>
                  <div className="flex justify-end gap-1.5">
                    <button
                      type="button"
                      onClick={() => aoEditar(u)}
                      disabled={ocupado}
                      aria-label={`Editar ${u.username}`}
                      title="Editar"
                      className="btn btn-sm btn-secundario"
                    >
                      <Pencil aria-hidden className="size-3.5" />
                      <span className="hidden 2xl:inline">Editar</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => aoRedefinirSenha(u)}
                      disabled={ocupado || proprio}
                      title={proprio ? MOTIVO_PROPRIO : "Resetar senha"}
                      aria-label={`Resetar senha de ${u.username}`}
                      className="btn btn-sm btn-secundario"
                    >
                      <KeyRound aria-hidden className="size-3.5" />
                      <span className="hidden 2xl:inline">Resetar senha</span>
                    </button>
                    {u.ativo ? (
                      <button
                        type="button"
                        onClick={() => aoDesativar(u)}
                        disabled={ocupado || proprio}
                        title={proprio ? MOTIVO_PROPRIO : "Desativar"}
                        aria-label={`Desativar ${u.username}`}
                        className="btn btn-sm btn-secundario enabled:hover:border-critico enabled:hover:text-critico-texto"
                      >
                        <UserX aria-hidden className="size-3.5" />
                        <span className="hidden 2xl:inline">Desativar</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => aoAtivar(u)}
                        disabled={ocupado}
                        aria-label={`Ativar ${u.username}`}
                        title="Ativar"
                        className="btn btn-sm btn-acento-suave"
                      >
                        <UserCheck aria-hidden className="size-3.5" />
                        <span className="hidden 2xl:inline">Ativar</span>
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
