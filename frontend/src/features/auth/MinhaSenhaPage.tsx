import { CircleCheck } from "lucide-react";
import { useState } from "react";

import { PaginaSimples } from "../../routes/PaginaSimples";
import { useSessao } from "./AuthContext";
import { FormTrocaSenha } from "./FormTrocaSenha";

export const TITULO_MINHA_SENHA = "Minha senha";
export const ROTA_MINHA_SENHA = "/minha-senha";


export function MinhaSenhaPage() {
  const { usuario } = useSessao();
  const [trocada, setTrocada] = useState(false);

  return (
    <PaginaSimples titulo={TITULO_MINHA_SENHA} subtitulo={`Usuário ${usuario.username}`}>
      <div className="mx-auto flex w-full max-w-sm flex-col gap-4 px-5 py-8">
        {trocada && (
          <div role="status" className="flex items-start gap-3 rounded-lg border border-bom/40 bg-bom/10 px-4 py-3">
            <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-bom-texto" />
            <p className="text-sm text-texto-2">
              Senha trocada. Use a nova senha no próximo login; as outras sessões abertas com a senha antiga foram
              encerradas.
            </p>
          </div>
        )}
        <FormTrocaSenha aoConcluir={() => setTrocada(true)} />
      </div>
    </PaginaSimples>
  );
}
