

import type { ErroPoliticaSenha, PermissoesUsuario, TokenAcesso, Usuario } from "../types/auth";
import { ApiError, getJson, postJson } from "./apiClient";

export const CAMINHO_LOGIN = "/api/v1/auth/login";
export const CAMINHO_ME = "/api/v1/auth/me";
export const CAMINHO_PERMISSOES = "/api/v1/auth/permissions";
export const CAMINHO_TROCA_SENHA = "/api/v1/auth/change-password";
export const CAMINHO_LOGOUT = "/api/v1/auth/logout";
export const CAMINHO_RENOVAR = "/api/v1/auth/renew";

export function login(username: string, password: string): Promise<TokenAcesso> {

  return postJson<TokenAcesso>(CAMINHO_LOGIN, { username, password }, { autenticado: false });
}


export function getMe(token?: string, signal?: AbortSignal): Promise<Usuario> {
  return getJson<Usuario>(CAMINHO_ME, { token, signal });
}

export function getPermissoes(token?: string, signal?: AbortSignal): Promise<PermissoesUsuario> {
  return getJson<PermissoesUsuario>(CAMINHO_PERMISSOES, { token, signal });
}


export function trocarSenha(senhaAtual: string, novaSenha: string): Promise<TokenAcesso> {
  return postJson<TokenAcesso>(CAMINHO_TROCA_SENHA, { current_password: senhaAtual, new_password: novaSenha });
}


export function renovar(): Promise<TokenAcesso> {
  return postJson<TokenAcesso>(CAMINHO_RENOVAR, undefined);
}


export async function logout(token: string): Promise<void> {
  try {
    await postJson<void>(CAMINHO_LOGOUT, undefined, { token, timeoutMs: 5_000 });
  } catch {
    // Falha ignorada de propósito.
  }
}


export function problemasDaSenha(erro: unknown): string[] {
  if (!(erro instanceof ApiError) || erro.status !== 422) return [];
  const corpo = erro.corpo as { detail?: Partial<ErroPoliticaSenha> } | null;
  const problemas = corpo?.detail?.problemas;
  return Array.isArray(problemas) ? problemas.filter((p): p is string => typeof p === "string") : [];
}
