import { Info, LoaderCircle, LogIn } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { Navigate } from "react-router";

import { CampoSenha } from "../../components/ui/CampoSenha";
import { ApiError } from "../../services/apiClient";
import { useAuth } from "./AuthContext";
import { AlertaAuth, AuthLayout, CampoAuth } from "./AuthLayout";

export const MSG_CREDENCIAIS = "Usuário ou senha inválidos.";
export const MSG_SESSAO_EXPIRADA = "Sua sessão expirou. Entre novamente.";
export const MSG_SAIU = "Você saiu do sistema.";


function mensagemDeErro(erro: unknown): string {
  if (erro instanceof ApiError) {
    if (erro.status === 401) return MSG_CREDENCIAIS;
    if (erro.status === 429) return erro.message;
    if (erro.tipo === "rede" || erro.tipo === "timeout") return erro.message;
  }
  return "Não foi possível entrar agora. Tente novamente em instantes.";
}

export function LoginPage() {
  const { estado, entrar } = useAuth();

  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const idUsuario = useId();
  const idSenha = useId();


  if (estado.status === "autenticado") return <Navigate to="/" replace />;

  const motivo = estado.status === "anonimo" ? estado.motivo : null;

  const aoEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (enviando) return;
    if (!usuario.trim() || !senha) {
      setErro("Informe usuário e senha.");
      return;
    }
    setEnviando(true);
    setErro(null);
    try {

      await entrar(usuario.trim(), senha);
    } catch (falha) {
      setSenha("");
      setErro(mensagemDeErro(falha));
      setEnviando(false);
    }
  };

  return (
    <AuthLayout titulo="Entrar" descricao="Use o usuário e a senha fornecidos pelo administrador.">
      {/* method="post": se algo falhar antes do JS, a senha não vai para a URL. */}
      <form method="post" noValidate onSubmit={aoEnviar} className="flex flex-col gap-4">
        {motivo && !erro && (
          <p
            role="status"
            className="flex items-start gap-2 rounded-lg border border-borda-forte bg-superficie-2 px-3 py-2.5 text-sm text-texto-2"
          >
            <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-acento-texto" />
            {motivo === "expirada" ? MSG_SESSAO_EXPIRADA : MSG_SAIU}
          </p>
        )}
        {erro && <AlertaAuth>{erro}</AlertaAuth>}

        <CampoAuth id={idUsuario} rotulo="Usuário">
          <input
            id={idUsuario}
            name="username"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            autoFocus
            maxLength={256}
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            disabled={enviando}
            aria-invalid={erro ? true : undefined}
            className="campo"
          />
        </CampoAuth>
        <CampoAuth id={idSenha} rotulo="Senha">
          <CampoSenha
            id={idSenha}
            name="password"
            autoComplete="current-password"
            maxLength={256}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            disabled={enviando}
            aria-invalid={erro ? true : undefined}
          />
        </CampoAuth>

        <button type="submit" disabled={enviando} aria-busy={enviando} className="btn btn-primario mt-2 w-full">
          {enviando ? (
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
          ) : (
            <LogIn aria-hidden className="size-4" />
          )}
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </AuthLayout>
  );
}
