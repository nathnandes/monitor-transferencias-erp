import { LogOut } from "lucide-react";

import { useSessao } from "./AuthContext";
import { AuthLayout } from "./AuthLayout";
import { FormTrocaSenha } from "./FormTrocaSenha";

export const TITULO_TROCA_SENHA = "Troque sua senha";


export function TrocaSenhaObrigatoriaPage() {
  const { usuario, sair } = useSessao();

  return (
    <AuthLayout
      titulo={TITULO_TROCA_SENHA}
      descricao={
        <>
          Olá, <strong className="text-texto">{usuario.nome_exibicao}</strong>. Por segurança, defina uma nova senha
          antes de continuar.
        </>
      }
    >
      <FormTrocaSenha
        acoes={
          <button type="button" onClick={sair} className="btn btn-fantasma w-full">
            <LogOut aria-hidden className="size-4" />
            Sair
          </button>
        }
      />
    </AuthLayout>
  );
}
