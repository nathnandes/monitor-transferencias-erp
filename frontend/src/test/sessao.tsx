

import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router";
import { vi } from "vitest";

import { AuthContext, type ValorAuth } from "../features/auth/AuthContext";
import type { Aba, Modulo, TokenAcesso, Usuario } from "../types/auth";

export const TODOS_MODULOS: Modulo[] = ["DASHBOARD", "TRANSFERENCIAS"];

export function usuarioTeste(parcial: Partial<Usuario> = {}): Usuario {
  return {
    id: 1,
    username: "maria",
    nome_exibicao: "Maria Silva",
    role: "OPERADOR",
    ativo: true,
    must_change_password: false,
    sessao_continua: false,
    ...parcial,
  };
}

export function tokenTeste(parcial: Partial<Usuario> = {}, accessToken = "token-de-teste"): TokenAcesso {
  return { access_token: accessToken, token_type: "bearer", expires_in: 1800, user: usuarioTeste(parcial) };
}


export function authFalso(
  modulos: Modulo[] = TODOS_MODULOS,
  usuario: Usuario = usuarioTeste(),
  abas: Aba[] | null = null,
): ValorAuth {
  return {
    estado: { status: "autenticado", usuario, modulos, abas },
    entrar: vi.fn(),
    sair: vi.fn(),
    trocarSenha: vi.fn(),
    tentarNovamente: vi.fn(),
  };
}


export function LocalAtual() {
  const { pathname } = useLocation();
  return <div data-testid="local">{pathname}</div>;
}

interface OpcoesRender {
  rota?: string;
  auth?: ValorAuth;
}

export function renderComSessao(ui: ReactElement, { rota = "/", auth = authFalso() }: OpcoesRender = {}) {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <AuthContext value={auth}>{ui}</AuthContext>
    </MemoryRouter>,
  );
}
