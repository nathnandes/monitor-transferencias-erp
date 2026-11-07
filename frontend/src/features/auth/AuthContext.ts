import { createContext, useContext } from "react";

import { abaLiberada } from "../../routes/abas";
import type { Aba, Modulo, Usuario } from "../../types/auth";


export type MotivoSaida = "expirada" | "logout";

export type EstadoAuth =

  | { status: "verificando" }
  | { status: "anonimo"; motivo: MotivoSaida | null }

  | { status: "erro"; erro: Error }
  | {
      status: "autenticado";
      usuario: Usuario;
      modulos: Modulo[];

      abas?: Aba[] | null;

      telaInicial?: string | null;
    };

export interface ValorAuth {
  estado: EstadoAuth;

  entrar: (username: string, password: string) => Promise<void>;

  sair: () => void;

  trocarSenha: (senhaAtual: string, novaSenha: string) => Promise<void>;

  tentarNovamente: () => void;
}

export const AuthContext = createContext<ValorAuth | null>(null);

export function useAuth(): ValorAuth {
  const valor = useContext(AuthContext);
  if (!valor) throw new Error("useAuth precisa estar dentro de <AuthProvider>.");
  return valor;
}

export interface Sessao {
  usuario: Usuario;
  modulos: Modulo[];

  abas: Aba[] | null;
  telaInicial: string | null;
  temModulo: (modulo: Modulo) => boolean;

  temAba: (aba: Aba) => boolean;
  sair: () => void;
}

function paraSessao(valor: ValorAuth | null): Sessao | null {
  if (!valor || valor.estado.status !== "autenticado") return null;
  const { usuario, modulos } = valor.estado;
  const abas = valor.estado.abas ?? null;
  return {
    usuario,
    modulos,
    abas,
    telaInicial: valor.estado.telaInicial ?? null,
    temModulo: (m) => modulos.includes(m),
    temAba: (a) => abaLiberada(a, modulos, abas),
    sair: valor.sair,
  };
}


export function useSessao(): Sessao {
  const sessao = paraSessao(useContext(AuthContext));
  if (!sessao) throw new Error("useSessao precisa de usuário autenticado (use dentro de <RequireAuth>).");
  return sessao;
}


export function useSessaoOpcional(): Sessao | null {
  return paraSessao(useContext(AuthContext));
}


export function useTemAba(aba: Aba): boolean {
  return useSessaoOpcional()?.temAba(aba) ?? true;
}
