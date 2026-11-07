

import { MODULOS } from "../../../routes/modulos";
import { ApiError } from "../../../services/apiClient";
import type { AtualizarUsuarioEntrada, Papel, PerfilResumo, UsuarioAdminDetalhe } from "../../../types/admin";
import type { Modulo } from "../../../types/auth";


const USERNAME_VALIDO = /^[a-z0-9._-]{3,50}$/;
export const NOME_MAX = 100;


export function normalizarUsername(valor: string): string {
  return valor.trim().toLowerCase();
}

export function erroUsername(valor: string): string | null {
  const username = normalizarUsername(valor);
  if (!username) return "Informe o username.";
  if (!USERNAME_VALIDO.test(username)) {
    return "Use de 3 a 50 caracteres: letras sem acento, números, ponto, hífen ou underscore.";
  }
  return null;
}

export function erroNome(valor: string): string | null {
  const nome = valor.trim();
  if (!nome) return "Informe o nome exibido.";
  if (nome.length > NOME_MAX) return `Use no máximo ${NOME_MAX} caracteres.`;
  return null;
}

export const ROTULO_PAPEL: Record<Papel, string> = { ADMIN: "Administrador", OPERADOR: "Operador" };


export function modulosIniciais(role: Papel): Modulo[] {
  return role === "ADMIN" ? ["DASHBOARD", "ADMINISTRACAO"] : [];
}


export function ajustarModulosAoPapel(modulos: readonly Modulo[], role: Papel): Modulo[] {
  const conjunto = new Set(modulos);
  if (role === "ADMIN") conjunto.add("ADMINISTRACAO");
  else conjunto.delete("ADMINISTRACAO");
  return ordenarModulos(conjunto);
}

export function ordenarModulos(modulos: Iterable<Modulo>): Modulo[] {
  const conjunto = new Set(modulos);
  return MODULOS.map((m) => m.modulo).filter((m) => conjunto.has(m));
}


export function sessaoContinuaPermitida(role: Papel): boolean {
  return role === "OPERADOR";
}

export interface FormEdicao {
  nome_exibicao: string;
  role: Papel;
  ativo: boolean;
  modulos: Modulo[];
  sessao_continua: boolean;

  perfil: PerfilResumo | null;
}


export function diferencasEdicao(original: UsuarioAdminDetalhe, form: FormEdicao): AtualizarUsuarioEntrada {
  const mudancas: AtualizarUsuarioEntrada = {};
  const nome = form.nome_exibicao.trim();
  if (nome !== original.nome_exibicao) mudancas.nome_exibicao = nome;
  if (form.role !== original.role) mudancas.role = form.role;
  if (form.ativo !== original.ativo) mudancas.ativo = form.ativo;
  if (form.sessao_continua !== original.sessao_continua) mudancas.sessao_continua = form.sessao_continua;
  const antes = ordenarModulos(original.modulos).join(",");
  const depois = ordenarModulos(form.modulos);
  if (depois.join(",") !== antes) mudancas.modulos = depois;
  const perfil = form.perfil?.id ?? null;
  if (perfil !== (original.perfil?.id ?? null)) mudancas.perfil_id = perfil;
  return mudancas;
}


export function mensagemErroAdmin(erro: unknown): string {
  if (erro instanceof ApiError) {
    if (erro.status === 401) return "Sua sessão expirou. Entre novamente.";
    if (erro.status === 403) return "Sem permissão: esta ação exige papel ADMIN com o módulo Administração.";
    return erro.message;
  }
  return "Não foi possível concluir a ação. Tente novamente.";
}
