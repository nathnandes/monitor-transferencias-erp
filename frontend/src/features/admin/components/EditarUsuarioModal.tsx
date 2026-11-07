import { LoaderCircle, Save } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Modal } from "../../../components/ui/Modal";
import { useAsync } from "../../../hooks/useAsync";
import { atualizarUsuario, obterUsuario } from "../../../services/adminUsuariosService";
import type { Papel, UsuarioAdminDetalhe } from "../../../types/admin";
import { ajustarModulosAoPapel, diferencasEdicao, erroNome, mensagemErroAdmin, type FormEdicao } from "../lib/regrasAdmin";
import { AlertaFormulario, Campo, OpcaoSessaoContinua, SeletorModulos, SeletorPapel, SeletorPerfil } from "./CamposFormulario";

export const AVISO_PROPRIO_USUARIO =
  "Você não pode mudar o próprio papel nem se desativar. Peça a outro ADMIN.";

interface EditarUsuarioModalProps {

  usuarioId: number | null;

  idProprio: number;
  aoFechar: () => void;
  aoSalvar: (usuario: UsuarioAdminDetalhe) => void;
}

export function EditarUsuarioModal({ usuarioId, idProprio, aoFechar, aoSalvar }: EditarUsuarioModalProps) {
  return (
    <Modal aberto={usuarioId !== null} titulo="Editar usuário" aoFechar={aoFechar} rotuloFechar="Fechar edição de usuário">
      {usuarioId !== null && (
        <CarregarUsuario usuarioId={usuarioId} idProprio={idProprio} aoFechar={aoFechar} aoSalvar={aoSalvar} />
      )}
    </Modal>
  );
}

function CarregarUsuario({ usuarioId, idProprio, aoFechar, aoSalvar }: EditarUsuarioModalProps & { usuarioId: number }) {

  const detalhe = useAsync((s) => obterUsuario(usuarioId, s), [usuarioId]);
  if (detalhe.loading && !detalhe.data) return <LoadingState rotulo="Carregando usuário…" />;
  if (detalhe.error || !detalhe.data) {
    return (
      <ErrorState
        titulo="Não foi possível carregar o usuário"
        mensagem={detalhe.error ? mensagemErroAdmin(detalhe.error) : undefined}
        erro={detalhe.error}
        aoTentarNovamente={detalhe.recarregar}
      />
    );
  }
  return (
    <FormEditar
      key={detalhe.data.id}
      original={detalhe.data}
      ehProprio={detalhe.data.id === idProprio}
      aoFechar={aoFechar}
      aoSalvar={aoSalvar}
    />
  );
}

interface FormEditarProps {
  original: UsuarioAdminDetalhe;
  ehProprio: boolean;
  aoFechar: () => void;
  aoSalvar: (usuario: UsuarioAdminDetalhe) => void;
}

function FormEditar({ original, ehProprio, aoFechar, aoSalvar }: FormEditarProps) {
  const [form, setForm] = useState<FormEdicao>({
    nome_exibicao: original.nome_exibicao,
    role: original.role,
    ativo: original.ativo,
    modulos: ajustarModulosAoPapel(original.modulos, original.role),
    sessao_continua: original.sessao_continua,
    perfil: original.perfil,
  });
  const [tentouEnviar, setTentouEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const idNome = useId();
  const idUsername = useId();
  const idAtivo = useId();

  const erroDoNome = tentouEnviar ? erroNome(form.nome_exibicao) : null;


  const mudarPapel = (role: Papel) =>
    setForm((f) => ({
      ...f,
      role,
      modulos: ajustarModulosAoPapel(f.modulos, role),
      sessao_continua: role === "ADMIN" ? false : f.sessao_continua,
    }));

  const aoEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (enviando) return;
    setTentouEnviar(true);
    setAviso(null);
    if (erroNome(form.nome_exibicao)) return;
    const mudancas = diferencasEdicao(original, form);
    if (Object.keys(mudancas).length === 0) {
      setAviso("Nada foi alterado.");
      return;
    }
    setEnviando(true);
    setFalha(null);
    try {

      aoSalvar(await atualizarUsuario(original.id, mudancas));
    } catch (erro) {
      setFalha(mensagemErroAdmin(erro));
      setEnviando(false);
    }
  };

  return (
    <form noValidate onSubmit={aoEnviar} className="flex flex-col gap-4">
      {falha && <AlertaFormulario mensagem={falha} />}
      {aviso && (
        <p role="status" className="text-sm text-texto-2">
          {aviso}
        </p>
      )}

      <div className="flex flex-col gap-1.5">
        <label htmlFor={idUsername} className="text-sm font-medium text-texto-2">
          Username
        </label>
        <input id={idUsername} value={original.username} readOnly className="campo font-mono opacity-80" />
      </div>
      <Campo id={idNome} rotulo="Nome exibido" erro={erroDoNome}>
        {(aria) => (
          <input
            id={idNome}
            type="text"
            autoComplete="off"
            autoFocus
            maxLength={256}
            value={form.nome_exibicao}
            onChange={(e) => setForm((f) => ({ ...f, nome_exibicao: e.target.value }))}
            disabled={enviando}
            className="campo"
            {...aria}
          />
        )}
      </Campo>
      <SeletorPapel
        valor={form.role}
        aoMudar={mudarPapel}
        desabilitado={enviando || ehProprio}
        dica={ehProprio ? AVISO_PROPRIO_USUARIO : "Ao virar ADMIN, ganha Administração; ao virar OPERADOR, perde."}
      />
      <label htmlFor={idAtivo} className="flex items-center gap-2 text-sm text-texto has-[:disabled]:opacity-60">
        <input
          id={idAtivo}
          type="checkbox"
          checked={form.ativo}
          onChange={(e) => setForm((f) => ({ ...f, ativo: e.target.checked }))}
          disabled={enviando || ehProprio}
          className="accent-acento"
        />
        Usuário ativo (inativo não consegue entrar e perde a sessão na hora)
      </label>
      <SeletorPerfil
        valor={form.perfil?.id ?? null}
        aoMudar={(perfil) => setForm((f) => ({ ...f, perfil: perfil && { id: perfil.id, nome: perfil.nome } }))}
        desabilitado={enviando}
      />
      <SeletorModulos
        role={form.role}
        valor={form.modulos}
        aoMudar={(modulos) => setForm((f) => ({ ...f, modulos }))}
        desabilitado={enviando}
        perfil={form.perfil?.nome}
      />
      <OpcaoSessaoContinua
        role={form.role}
        valor={form.sessao_continua}
        aoMudar={(sessao_continua) => setForm((f) => ({ ...f, sessao_continua }))}
        desabilitado={enviando}
      />

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={aoFechar} disabled={enviando} className="btn btn-fantasma">
          Cancelar
        </button>
        <button type="submit" disabled={enviando} aria-busy={enviando} className="btn btn-primario">
          {enviando ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : <Save aria-hidden className="size-4" />}
          {enviando ? "Salvando…" : "Salvar alterações"}
        </button>
      </div>
    </form>
  );
}
