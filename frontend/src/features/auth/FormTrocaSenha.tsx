import { Check, KeyRound, LoaderCircle, X } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { CampoSenha } from "../../components/ui/CampoSenha";
import { ApiError } from "../../services/apiClient";
import { problemasDaSenha } from "../../services/authService";
import { useAuth } from "./AuthContext";
import { AlertaAuth, CampoAuth } from "./AuthLayout";
import { REGRAS_SENHA, senhaAtendePolitica } from "./regrasSenha";

interface Falha {
  mensagem: string;
  problemas: string[];
}

function descreverFalha(erro: unknown): Falha {
  if (erro instanceof ApiError) {

    if (erro.status === 400 || erro.status === 422 || erro.status === 429 || erro.tipo !== "http") {
      return { mensagem: erro.message, problemas: problemasDaSenha(erro) };
    }
  }
  return { mensagem: "Não foi possível trocar a senha agora. Tente novamente.", problemas: [] };
}

interface FormTrocaSenhaProps {

  aoConcluir?: () => void;

  acoes?: ReactNode;
}


export function FormTrocaSenha({ aoConcluir, acoes }: FormTrocaSenhaProps) {
  const { trocarSenha } = useAuth();
  const [atual, setAtual] = useState("");
  const [nova, setNova] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<Falha | null>(null);
  const idAtual = useId();
  const idNova = useId();
  const idConfirmacao = useId();
  const idRegras = useId();

  const confirmacaoConfere = confirmacao.length > 0 && confirmacao === nova;
  const podeEnviar = atual.length > 0 && senhaAtendePolitica(nova, atual) && confirmacaoConfere && !enviando;

  const aoEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!podeEnviar) return;
    setEnviando(true);
    setFalha(null);
    try {
      await trocarSenha(atual, nova);
    } catch (erro) {
      setFalha(descreverFalha(erro));
      setAtual("");
      setNova("");
      setConfirmacao("");
      setEnviando(false);
      return;
    }
    setAtual("");
    setNova("");
    setConfirmacao("");
    setEnviando(false);
    aoConcluir?.();
  };

  return (
    <form method="post" noValidate onSubmit={aoEnviar} className="flex flex-col gap-4">
      {falha && (
        <AlertaAuth>
          <p>{falha.mensagem}</p>
          {falha.problemas.length > 0 && (
            <ul className="mt-1 list-disc pl-5">
              {falha.problemas.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </AlertaAuth>
      )}

      <CampoAuth id={idAtual} rotulo="Senha atual">
        <CampoSenha
          id={idAtual}
          name="current-password"
          autoComplete="current-password"
          autoFocus
          maxLength={256}
          value={atual}
          onChange={(e) => setAtual(e.target.value)}
          disabled={enviando}
        />
      </CampoAuth>
      <CampoAuth id={idNova} rotulo="Nova senha">
        <CampoSenha
          id={idNova}
          name="new-password"
          autoComplete="new-password"
          maxLength={256}
          value={nova}
          onChange={(e) => setNova(e.target.value)}
          disabled={enviando}
          aria-describedby={idRegras}
        />
      </CampoAuth>

      <div id={idRegras} className="rounded-lg border border-borda bg-superficie-2/40 px-3 py-2.5">
        <p className="text-xs font-semibold text-texto-2">A nova senha precisa ter:</p>
        <ul aria-label="Regras da nova senha" className="mt-1.5 flex flex-col gap-1">
          {REGRAS_SENHA.map((regra) => {
            const ok = regra.atende(nova, atual);
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

      <CampoAuth id={idConfirmacao} rotulo="Confirme a nova senha">
        <CampoSenha
          id={idConfirmacao}
          name="confirm-password"
          autoComplete="new-password"
          maxLength={256}
          value={confirmacao}
          onChange={(e) => setConfirmacao(e.target.value)}
          disabled={enviando}
          aria-invalid={confirmacao.length > 0 && !confirmacaoConfere ? true : undefined}
        />
      </CampoAuth>
      {confirmacao.length > 0 && !confirmacaoConfere && (
        <p className="-mt-2 text-xs text-critico-texto">A confirmação não confere com a nova senha.</p>
      )}

      <button type="submit" disabled={!podeEnviar} aria-busy={enviando} className="btn btn-primario mt-2 w-full">
        {enviando ? (
          <LoaderCircle aria-hidden className="size-4 animate-spin" />
        ) : (
          <KeyRound aria-hidden className="size-4" />
        )}
        {enviando ? "Salvando…" : "Salvar nova senha"}
      </button>
      {acoes}
    </form>
  );
}
