

import type {
  AtualizarUsuarioEntrada,
  CriarUsuarioEntrada,
  FiltrosUsuarios,
  PaginaUsuarios,
  PerfilAdmin,
  PerfilEntrada,
  UsuarioAdminDetalhe,
} from "../types/admin";
import { deleteJson, getJson, patchJson, postJson, putJson } from "./apiClient";

export const CAMINHO_ADMIN_USUARIOS = "/api/v1/admin/users";

export const TAMANHO_PAGINA_MAXIMO_USUARIOS = 100;

const caminhoUsuario = (id: number) => `${CAMINHO_ADMIN_USUARIOS}/${id}`;

export function listarUsuarios(
  filtros: FiltrosUsuarios,
  pagina = 1,
  tamanhoPagina = 20,
  signal?: AbortSignal,
): Promise<PaginaUsuarios> {
  const tamanho = Math.min(Math.max(1, Math.trunc(tamanhoPagina)), TAMANHO_PAGINA_MAXIMO_USUARIOS);
  return getJson<PaginaUsuarios>(CAMINHO_ADMIN_USUARIOS, {
    params: {
      busca: filtros.busca.trim().slice(0, 100),
      role: filtros.role,
      ativo: filtros.ativo,
      pagina: Math.max(1, Math.trunc(pagina)),
      tamanho_pagina: tamanho,
    },
    signal,
  });
}

export function obterUsuario(id: number, signal?: AbortSignal): Promise<UsuarioAdminDetalhe> {
  return getJson<UsuarioAdminDetalhe>(caminhoUsuario(id), { signal });
}

export function criarUsuario(dados: CriarUsuarioEntrada): Promise<UsuarioAdminDetalhe> {
  return postJson<UsuarioAdminDetalhe>(CAMINHO_ADMIN_USUARIOS, dados);
}

export function atualizarUsuario(id: number, dados: AtualizarUsuarioEntrada): Promise<UsuarioAdminDetalhe> {
  return patchJson<UsuarioAdminDetalhe>(caminhoUsuario(id), dados);
}

export function redefinirSenha(id: number, senha: string, exigirTroca: boolean): Promise<UsuarioAdminDetalhe> {
  return postJson<UsuarioAdminDetalhe>(`${caminhoUsuario(id)}/reset-password`, {
    password_temporaria: senha,
    exigir_troca_senha: exigirTroca,
  });
}

export function ativarUsuario(id: number): Promise<UsuarioAdminDetalhe> {
  return postJson<UsuarioAdminDetalhe>(`${caminhoUsuario(id)}/activate`);
}

export function desativarUsuario(id: number): Promise<UsuarioAdminDetalhe> {
  return postJson<UsuarioAdminDetalhe>(`${caminhoUsuario(id)}/deactivate`);
}

export const CAMINHO_ADMIN_PERFIS = "/api/v1/admin/perfis";

export function listarPerfis(signal?: AbortSignal): Promise<PerfilAdmin[]> {
  return getJson<PerfilAdmin[]>(CAMINHO_ADMIN_PERFIS, { signal });
}

export function criarPerfil(dados: PerfilEntrada): Promise<PerfilAdmin> {
  return postJson<PerfilAdmin>(CAMINHO_ADMIN_PERFIS, dados);
}


export function atualizarPerfil(id: number, dados: PerfilEntrada): Promise<PerfilAdmin> {
  return putJson<PerfilAdmin>(`${CAMINHO_ADMIN_PERFIS}/${id}`, dados);
}


export function excluirPerfil(id: number): Promise<void> {
  return deleteJson(`${CAMINHO_ADMIN_PERFIS}/${id}`);
}
