import { Check, X } from "lucide-react";
import { useId, type ReactNode } from "react";

import { useAsync } from "../../../hooks/useAsync";
import { MODULOS } from "../../../routes/modulos";
import { listarPerfis } from "../../../services/adminUsuariosService";
import type { Papel, PerfilAdmin } from "../../../types/admin";
import type { Modulo } from "../../../types/auth";
import { REGRAS_POLITICA } from "../../auth/regrasSenha";

interface CampoProps {
  id: string;
  rotulo: string;

  erro?: string | null;
  dica?: ReactNode;
  children: (aria: { "aria-invalid"?: true; "aria-describedby"?: string }) => ReactNode;
}


export function Campo({ id, rotulo, erro, dica, children }: CampoProps) {
  const idDica = `${id}-dica`;
  const idErro = `${id}-erro`;
  const descritores = [dica ? idDica : null, erro ? idErro : null].filter(Boolean).join(" ");
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-texto-2">
        {rotulo}
      </label>
      {children({
        "aria-invalid": erro ? true : undefined,
        "aria-describedby": descritores || undefined,
      })}
      {dica && (
        <p id={idDica} className="text-xs text-texto-mudo">
          {dica}
        </p>
      )}
      {erro && (
        <p id={idErro} className="text-xs text-critico-texto">
          {erro}
        </p>
      )}
    </div>
  );
}

export function SeletorPapel({
  valor,
  aoMudar,
  desabilitado = false,
  dica,
}: {
  valor: Papel;
  aoMudar: (papel: Papel) => void;
  desabilitado?: boolean;
  dica?: string;
}) {
  const nome = useId();
  const idDica = useId();
  return (
    <fieldset className="flex flex-col gap-1.5" aria-describedby={dica ? idDica : undefined}>
      <legend className="mb-1.5 text-sm font-medium text-texto-2">Papel</legend>
      <div className="flex gap-2">
        {(["OPERADOR", "ADMIN"] as const).map((papel) => (
          <label
            key={papel}
            className={`flex flex-1 cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60 ${
              valor === papel ? "border-acento bg-acento-suave text-acento-texto" : "border-borda-forte bg-superficie-2 text-texto-2"
            }`}
          >
            <input
              type="radio"
              name={nome}
              value={papel}
              checked={valor === papel}
              onChange={() => aoMudar(papel)}
              disabled={desabilitado}
              className="accent-acento"
            />
            {papel}
          </label>
        ))}
      </div>
      {dica && (
        <p id={idDica} className="text-xs text-texto-mudo">
          {dica}
        </p>
      )}
    </fieldset>
  );
}


export function SeletorPerfil({
  valor,
  aoMudar,
  desabilitado = false,
}: {
  valor: number | null;
  aoMudar: (perfil: PerfilAdmin | null) => void;
  desabilitado?: boolean;
}) {
  const id = useId();
  const idDica = useId();
  const perfis = useAsync((s) => listarPerfis(s), []);
  const lista = perfis.data ?? [];
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-texto-2">
        Perfil de acesso
      </label>
      <select
        id={id}
        value={valor ?? ""}
        onChange={(e) => aoMudar(lista.find((p) => String(p.id) === e.target.value) ?? null)}
        disabled={desabilitado || (perfis.loading && !perfis.data)}
        aria-describedby={idDica}
        className="campo"
      >
        <option value="">Sem perfil (módulos marcados abaixo, todas as abas)</option>
        {lista.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nome}
          </option>
        ))}
      </select>
      <p id={idDica} className="text-xs text-texto-mudo">
        {perfis.error
          ? "Não foi possível carregar os perfis."
          : "Com perfil, as abas, sub-abas e a tela que abre no login vêm dele (Administração › Perfis)."}
      </p>
    </div>
  );
}


export function SeletorModulos({
  role,
  valor,
  aoMudar,
  desabilitado = false,
  perfil = null,
}: {
  role: Papel;
  valor: readonly Modulo[];
  aoMudar: (modulos: Modulo[]) => void;
  desabilitado?: boolean;

  perfil?: string | null;
}) {
  const alternar = (modulo: Modulo, marcado: boolean) => {
    const conjunto = new Set(valor);
    if (marcado) conjunto.add(modulo);
    else conjunto.delete(modulo);
    aoMudar(MODULOS.map((m) => m.modulo).filter((m) => conjunto.has(m)));
  };

  return (
    <fieldset className="rounded-lg border border-borda bg-superficie-2/30 p-3">
      <legend className="px-1 text-sm font-medium text-texto-2">Permissões por módulo</legend>
      {perfil && (
        <p className="mb-2 px-1 text-xs text-texto-mudo">
          Com o perfil {perfil}, os módulos vêm dele. Estes ficam guardados e voltam a valer se o perfil sair.
        </p>
      )}
      <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {MODULOS.map(({ modulo, rotulo }) => {
          const ehAdministracao = modulo === "ADMINISTRACAO";
          const marcado = ehAdministracao ? role === "ADMIN" : valor.includes(modulo);
          return (
            <li key={modulo}>
              <label className="flex cursor-pointer items-start gap-2 rounded-md px-1.5 py-1 text-sm text-texto has-[:disabled]:cursor-not-allowed">
                <input
                  type="checkbox"
                  checked={marcado}
                  onChange={(e) => alternar(modulo, e.target.checked)}
                  disabled={desabilitado || ehAdministracao || Boolean(perfil)}
                  className="mt-0.5 accent-acento"
                />
                <span>
                  {rotulo}
                  {ehAdministracao && (
                    <span className="block text-[11px] text-texto-mudo">
                      {role === "ADMIN" ? "Sempre liberado para ADMIN." : "Não permitido para OPERADOR."}
                    </span>
                  )}
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}


export function OpcaoSessaoContinua({
  role,
  valor,
  aoMudar,
  desabilitado = false,
}: {
  role: Papel;
  valor: boolean;
  aoMudar: (valor: boolean) => void;
  desabilitado?: boolean;
}) {
  const id = useId();
  const idDica = useId();
  const soOperador = role !== "OPERADOR";
  return (
    <div className="rounded-lg border border-borda bg-superficie-2/30 p-3">
      <label htmlFor={id} className="flex cursor-pointer items-center gap-2 text-sm font-medium text-texto has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
        <input
          id={id}
          type="checkbox"
          checked={valor && !soOperador}
          onChange={(e) => aoMudar(e.target.checked)}
          disabled={desabilitado || soOperador}
          aria-describedby={idDica}
          className="accent-acento"
        />
        Sessão contínua (modo TV)
      </label>
      <p id={idDica} className="mt-1 pl-6 text-xs text-texto-mudo">
        {soOperador
          ? "Só para OPERADOR: uma sessão de administrador aberta numa TV daria acesso à administração."
          : "Para um monitor da loja: a sessão se renova sozinha e só termina quando alguém clica em Sair. Desativar o usuário, redefinir a senha ou desmarcar esta opção também encerra."}
      </p>
    </div>
  );
}


export function OpcaoExigirTroca({
  valor,
  aoMudar,
  desabilitado = false,
}: {
  valor: boolean;
  aoMudar: (valor: boolean) => void;
  desabilitado?: boolean;
}) {
  const id = useId();
  const idDica = useId();
  return (
    <div className="rounded-lg border border-borda bg-superficie-2/30 p-3">
      <label htmlFor={id} className="flex cursor-pointer items-center gap-2 text-sm font-medium text-texto has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
        <input
          id={id}
          type="checkbox"
          checked={valor}
          onChange={(e) => aoMudar(e.target.checked)}
          disabled={desabilitado}
          aria-describedby={idDica}
          className="accent-acento"
        />
        Exigir troca de senha no próximo acesso
      </label>
      <p id={idDica} className="mt-1 pl-6 text-xs text-texto-mudo">
        {valor
          ? "Ao entrar, a pessoa terá de definir uma senha própria antes de usar o sistema."
          : "A pessoa entra direto com esta senha e pode trocá-la quando quiser, em “Minha senha”."}
      </p>
    </div>
  );
}

interface CamposSenhaProps {
  senha: string;
  confirmacao: string;
  aoMudarSenha: (valor: string) => void;
  aoMudarConfirmacao: (valor: string) => void;
  desabilitado?: boolean;

  mostrarErros: boolean;
}


export function CamposSenhaTemporaria({
  senha,
  confirmacao,
  aoMudarSenha,
  aoMudarConfirmacao,
  desabilitado = false,
  mostrarErros,
}: CamposSenhaProps) {
  const idSenha = useId();
  const idConfirmacao = useId();
  const idRegras = useId();
  const atendeTudo = REGRAS_POLITICA.every((r) => r.atende(senha, ""));
  const erroSenha = mostrarErros && !atendeTudo ? "A senha não atende às regras abaixo." : null;
  const erroConfirmacao =
    (mostrarErros || confirmacao.length > 0) && confirmacao !== senha
      ? "A confirmação não confere com a senha."
      : null;

  return (
    <>
      <Campo id={idSenha} rotulo="Senha" erro={erroSenha}>
        {(aria) => (
          <input
            id={idSenha}
            type="password"
            autoComplete="new-password"
            maxLength={256}
            value={senha}
            onChange={(e) => aoMudarSenha(e.target.value)}
            disabled={desabilitado}
            className="campo"
            {...aria}
            aria-describedby={[idRegras, aria["aria-describedby"]].filter(Boolean).join(" ")}
          />
        )}
      </Campo>
      <div id={idRegras} className="rounded-lg border border-borda bg-superficie-2/40 px-3 py-2.5">
        <p className="text-xs font-semibold text-texto-2">A senha precisa ter:</p>
        <ul aria-label="Regras da senha" className="mt-1.5 flex flex-col gap-1">
          {REGRAS_POLITICA.map((regra) => {
            const ok = regra.atende(senha, "");
            const Icone = ok ? Check : X;
            return (
              <li
                key={regra.id}
                data-atende={ok}
                className={`flex items-center gap-2 text-xs ${ok ? "text-bom-texto" : "text-texto-mudo"}`}
              >
                <Icone aria-hidden className="size-3.5 shrink-0" />
                {regra.texto}
                <span className="sr-only">{ok ? " (atendida)" : " (pendente)"}</span>
              </li>
            );
          })}
        </ul>
      </div>
      <Campo id={idConfirmacao} rotulo="Confirme a senha" erro={erroConfirmacao}>
        {(aria) => (
          <input
            id={idConfirmacao}
            type="password"
            autoComplete="new-password"
            maxLength={256}
            value={confirmacao}
            onChange={(e) => aoMudarConfirmacao(e.target.value)}
            disabled={desabilitado}
            className="campo"
            {...aria}
          />
        )}
      </Campo>
    </>
  );
}


export function AlertaFormulario({ mensagem, problemas = [] }: { mensagem: string; problemas?: string[] }) {
  return (
    <div role="alert" className="rounded-lg border border-critico/40 bg-critico/10 px-3 py-2.5 text-sm text-critico-texto">
      <p>{mensagem}</p>
      {problemas.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {problemas.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
