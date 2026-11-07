import { Compass, Construction, KeyRound, ShieldX } from "lucide-react";
import { Link } from "react-router";

import { EmptyState } from "../components/ui/EmptyState";
import { useSessao } from "../features/auth/AuthContext";
import { PaginaSimples } from "./PaginaSimples";
import type { InfoModulo } from "./modulos";

export const TITULO_403 = "Acesso negado";


export function AcessoNegadoPage() {
  const { usuario } = useSessao();
  return (
    <PaginaSimples titulo={TITULO_403} subtitulo="Erro 403 · sem permissão para este módulo">
      <EmptyState
        icone={ShieldX}
        titulo="Você não tem permissão para acessar esta página."
        descricao={`O usuário ${usuario.username} não tem este módulo liberado. Se precisa dele, peça acesso ao administrador do sistema.`}
        acao={
          <Link to="/" className="btn btn-secundario">
            Voltar ao início
          </Link>
        }
      />
    </PaginaSimples>
  );
}


export function EmDesenvolvimentoPage({ info }: { info: InfoModulo }) {
  return (
    <PaginaSimples titulo={info.rotulo} subtitulo="Módulo liberado para o seu usuário">
      <EmptyState
        icone={Construction}
        titulo="Em desenvolvimento"
        descricao={`O módulo ${info.rotulo} ainda não tem tela. Ele aparecerá aqui quando estiver pronto.`}
      />
    </PaginaSimples>
  );
}


export function SemModulosPage() {
  return (
    <PaginaSimples titulo="Nenhum módulo liberado">
      <EmptyState
        icone={KeyRound}
        titulo="Seu usuário ainda não tem módulos liberados."
        descricao="Peça ao administrador do sistema para conceder o acesso aos módulos de que você precisa."
      />
    </PaginaSimples>
  );
}

export function NaoEncontradaPage() {
  return (
    <PaginaSimples titulo="Página não encontrada" subtitulo="Erro 404">
      <EmptyState
        icone={Compass}
        titulo="Este endereço não existe."
        acao={
          <Link to="/" className="btn btn-secundario">
            Voltar ao início
          </Link>
        }
      />
    </PaginaSimples>
  );
}
