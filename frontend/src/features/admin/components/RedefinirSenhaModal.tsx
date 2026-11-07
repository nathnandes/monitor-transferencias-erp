import { KeyRound, LoaderCircle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Modal } from "../../../components/ui/Modal";
import { problemasDaSenha } from "../../../services/authService";
import { redefinirSenha } from "../../../services/adminUsuariosService";
import type { UsuarioAdmin, UsuarioAdminDetalhe } from "../../../types/admin";
import { senhaTemporariaValida } from "../../auth/regrasSenha";
import { mensagemErroAdmin } from "../lib/regrasAdmin";
import { AlertaFormulario, CamposSenhaTemporaria, OpcaoExigirTroca } from "./CamposFormulario";

interface RedefinirSenhaModalProps {

  usuario: UsuarioAdmin | null;
  aoFechar: () => void;
  aoRedefinir: (usuario: UsuarioAdminDetalhe) => void;
}

export function RedefinirSenhaModal({ usuario, aoFechar, aoRedefinir }: RedefinirSenhaModalProps) {
  return (
    <Modal aberto={usuario !== null} titulo="Redefinir senha" aoFechar={aoFechar} rotuloFechar="Fechar redefinição de senha">
      {usuario && <FormRedefinir usuario={usuario} aoFechar={aoFechar} aoRedefinir={aoRedefinir} />}
    </Modal>
  );
}

interface Falha {
  mensagem: string;
  problemas: string[];
}

function FormRedefinir({ usuario, aoFechar, aoRedefinir }: RedefinirSenhaModalProps & { usuario: UsuarioAdmin }) {
  const [senha, setSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [exigirTroca, setExigirTroca] = useState(false);
  const [tentouEnviar, setTentouEnviar] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<Falha | null>(null);

  const aoEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (enviando) return;
    setTentouEnviar(true);
    if (!senhaTemporariaValida(senha) || senha !== confirmacao) return;

    setEnviando(true);
    setFalha(null);
    const senhaEnviada = senha;
    setSenha("");
    setConfirmacao("");
    try {
      aoRedefinir(await redefinirSenha(usuario.id, senhaEnviada, exigirTroca));
    } catch (erro) {
      setFalha({ mensagem: mensagemErroAdmin(erro), problemas: problemasDaSenha(erro) });
      setTentouEnviar(false);
      setEnviando(false);
    }
  };

  return (
    <form method="post" noValidate onSubmit={aoEnviar} className="flex flex-col gap-4">
      <p className="text-sm text-texto-2">
        Nova senha para <strong className="font-mono text-texto">{usuario.username}</strong>. As sessões abertas
        dessa pessoa deixam de valer na hora.
      </p>
      {falha && <AlertaFormulario mensagem={falha.mensagem} problemas={falha.problemas} />}
      <CamposSenhaTemporaria
        senha={senha}
        confirmacao={confirmacao}
        aoMudarSenha={setSenha}
        aoMudarConfirmacao={setConfirmacao}
        desabilitado={enviando}
        mostrarErros={tentouEnviar}
      />
      <OpcaoExigirTroca valor={exigirTroca} aoMudar={setExigirTroca} desabilitado={enviando} />
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={aoFechar} disabled={enviando} className="btn btn-fantasma">
          Cancelar
        </button>
        <button type="submit" disabled={enviando} aria-busy={enviando} className="btn btn-primario">
          {enviando ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : <KeyRound aria-hidden className="size-4" />}
          {enviando ? "Redefinindo…" : "Redefinir senha"}
        </button>
      </div>
    </form>
  );
}
