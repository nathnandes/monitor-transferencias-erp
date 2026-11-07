import { CircleCheck, LoaderCircle, UserPlus } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { Modal } from "../../../components/ui/Modal";
import { problemasDaSenha } from "../../../services/authService";
import { criarUsuario } from "../../../services/adminUsuariosService";
import type { Papel, PerfilResumo, UsuarioAdminDetalhe } from "../../../types/admin";
import type { Modulo } from "../../../types/auth";
import { senhaTemporariaValida } from "../../auth/regrasSenha";
import {
  ajustarModulosAoPapel,
  erroNome,
  erroUsername,
  mensagemErroAdmin,
  modulosIniciais,
  normalizarUsername,
  sessaoContinuaPermitida,
} from "../lib/regrasAdmin";
import {
  AlertaFormulario,
  Campo,
  CamposSenhaTemporaria,
  OpcaoExigirTroca,
  OpcaoSessaoContinua,
  SeletorModulos,
  SeletorPapel,
  SeletorPerfil,
} from "./CamposFormulario";

export const AVISO_PRIMEIRO_LOGIN =
  "No primeiro login, a pessoa deverá trocar a senha por uma senha própria.";
export const AVISO_SEM_TROCA = "A pessoa já pode entrar com esta senha e trocá-la quando quiser, em “Minha senha”.";

interface CriarUsuarioModalProps {
  aberto: boolean;
  aoFechar: () => void;

  aoCriar: (usuario: UsuarioAdminDetalhe) => void;
}

export function CriarUsuarioModal({ aberto, aoFechar, aoCriar }: CriarUsuarioModalProps) {

  return (
    <Modal aberto={aberto} titulo="Criar usuário" aoFechar={aoFechar} rotuloFechar="Fechar criação de usuário">
      <FormCriar aoFechar={aoFechar} aoCriar={aoCriar} />
    </Modal>
  );
}

interface Falha {
  mensagem: string;
  problemas: string[];
}

function FormCriar({ aoFechar, aoCriar }: Omit<CriarUsuarioModalProps, "aberto">) {
  const [username, setUsername] = useState("");
  const [nome, setNome] = useState("");
  const [role, setRole] = useState<Papel>("OPERADOR");
  const [modulos, setModulos] = useState<Modulo[]>(modulosIniciais("OPERADOR"));
  const [sessaoContinua, setSessaoContinua] = useState(false);
  const [perfil, setPerfil] = useState<PerfilResumo | null>(null);
  const [exigirTroca, setExigirTroca] = useState(false);
  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [tentouEnviar, setTentouEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<Falha | null>(null);
  const [criado, setCriado] = useState<UsuarioAdminDetalhe | null>(null);
  const idUsername = useId();
  const idNome = useId();

  const erros = {
    username: tentouEnviar ? erroUsername(username) : null,
    nome: tentouEnviar ? erroNome(nome) : null,
  };

  const mudarPapel = (novo: Papel) => {
    setRole(novo);

    setModulos((atuais) => ajustarModulosAoPapel(novo === "ADMIN" ? [...atuais, ...modulosIniciais("ADMIN")] : atuais, novo));
  };

  const aoEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (enviando) return;
    setTentouEnviar(true);
    const valido =
      !erroUsername(username) && !erroNome(nome) && senhaTemporariaValida(senha) && senha === confirmacao;
    if (!valido) return;

    setEnviando(true);
    setFalha(null);
    const dados = {
      username: normalizarUsername(username),
      nome_exibicao: nome.trim(),
      password_temporaria: senha,
      role,
      modulos: ajustarModulosAoPapel(modulos, role),
      sessao_continua: sessaoContinua && sessaoContinuaPermitida(role),
      exigir_troca_senha: exigirTroca,
      perfil_id: perfil?.id ?? null,
    };

    setSenha("");
    setConfirmacao("");
    try {
      const usuario = await criarUsuario(dados);
      setCriado(usuario);
      aoCriar(usuario);
    } catch (erro) {
      setFalha({ mensagem: mensagemErroAdmin(erro), problemas: problemasDaSenha(erro) });
      setTentouEnviar(false);
    } finally {
      setEnviando(false);
    }
  };

  if (criado) {
    return (
      <div role="status" className="flex flex-col items-start gap-4">
        <div className="flex items-start gap-3 rounded-lg border border-bom/40 bg-bom/10 px-4 py-3">
          <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-bom-texto" />
          <div className="text-sm text-texto-2">
            <p className="font-semibold text-texto">
              Usuário <span className="font-mono">{criado.username}</span> criado como {criado.role}.
            </p>
            <p className="mt-1">{criado.must_change_password ? AVISO_PRIMEIRO_LOGIN : AVISO_SEM_TROCA}</p>
            <p className="mt-1 text-xs text-texto-mudo">
              Informe a senha à pessoa pessoalmente ou por um canal seguro. Ela não é exibida nem guardada por esta tela.
            </p>
          </div>
        </div>
        <button type="button" onClick={aoFechar} className="btn btn-primario">
          Fechar
        </button>
      </div>
    );
  }

  return (
    <form method="post" noValidate onSubmit={aoEnviar} className="flex flex-col gap-4">
      {falha && <AlertaFormulario mensagem={falha.mensagem} problemas={falha.problemas} />}

      <Campo
        id={idUsername}
        rotulo="Username"
        erro={erros.username}
        dica="3 a 50 caracteres: letras sem acento, números, ponto, hífen ou underscore. Não pode ser alterado depois."
      >
        {(aria) => (
          <input
            id={idUsername}
            type="text"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            maxLength={256}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={enviando}
            className="campo"
            {...aria}
          />
        )}
      </Campo>
      <Campo id={idNome} rotulo="Nome exibido" erro={erros.nome}>
        {(aria) => (
          <input
            id={idNome}
            type="text"
            autoComplete="off"
            maxLength={256}
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            disabled={enviando}
            className="campo"
            {...aria}
          />
        )}
      </Campo>
      <SeletorPapel
        valor={role}
        aoMudar={mudarPapel}
        desabilitado={enviando}
        dica="ADMIN administra usuários; OPERADOR usa só os módulos liberados."
      />
      <CamposSenhaTemporaria
        senha={senha}
        confirmacao={confirmacao}
        aoMudarSenha={setSenha}
        aoMudarConfirmacao={setConfirmacao}
        desabilitado={enviando}
        mostrarErros={tentouEnviar}
      />
      <SeletorPerfil valor={perfil?.id ?? null} aoMudar={setPerfil} desabilitado={enviando} />
      <SeletorModulos role={role} valor={modulos} aoMudar={setModulos} desabilitado={enviando} perfil={perfil?.nome} />
      <OpcaoExigirTroca valor={exigirTroca} aoMudar={setExigirTroca} desabilitado={enviando} />
      <OpcaoSessaoContinua role={role} valor={sessaoContinua} aoMudar={setSessaoContinua} desabilitado={enviando} />

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={aoFechar} disabled={enviando} className="btn btn-fantasma">
          Cancelar
        </button>
        <button type="submit" disabled={enviando} aria-busy={enviando} className="btn btn-primario">
          {enviando ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : <UserPlus aria-hidden className="size-4" />}
          {enviando ? "Criando…" : "Criar usuário"}
        </button>
      </div>
    </form>
  );
}
