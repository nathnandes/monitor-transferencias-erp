import { LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, Outlet } from "react-router";

import { ErrorState } from "../components/ui/ErrorState";
import { LoadingState } from "../components/ui/LoadingState";
import { useAuth, useSessao } from "../features/auth/AuthContext";
import { TrocaSenhaObrigatoriaPage } from "../features/auth/TrocaSenhaObrigatoriaPage";
import type { Aba } from "../types/auth";
import { podeAcessar, rotaInicial, type InfoModulo } from "./modulos";
import { AcessoNegadoPage, SemModulosPage } from "./paginas";

function TelaCheia({ children }: { children: ReactNode }) {
  return <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4">{children}</div>;
}


export function RequireAuth() {
  const { estado, tentarNovamente, sair } = useAuth();

  switch (estado.status) {
    case "verificando":
      return (
        <TelaCheia>
          <LoadingState rotulo="Verificando sessão…" />
        </TelaCheia>
      );
    case "erro":
      return (
        <TelaCheia>
          <div className="w-full max-w-md">
            <ErrorState titulo="Não foi possível verificar a sessão" erro={estado.erro} aoTentarNovamente={tentarNovamente} />
          </div>
          <button type="button" onClick={sair} className="btn btn-fantasma">
            <LogOut aria-hidden className="size-4" />
            Sair
          </button>
        </TelaCheia>
      );
    case "anonimo":
      return <Navigate to="/login" replace />;
    case "autenticado":
      if (estado.usuario.must_change_password) return <TrocaSenhaObrigatoriaPage />;
      return <Outlet />;
  }
}


export function RequireModulo({ info, aba, children }: { info: InfoModulo; aba?: Aba; children: ReactNode }) {
  const { modulos, usuario, temAba } = useSessao();
  const liberado = podeAcessar(info, modulos, usuario.role) && (!aba || temAba(aba));
  return liberado ? children : <AcessoNegadoPage />;
}


export function RotaInicial() {
  const { modulos, usuario, telaInicial, abas } = useSessao();
  const destino = rotaInicial(modulos, usuario.role, telaInicial, abas);
  return destino ? <Navigate to={destino} replace /> : <SemModulosPage />;
}
