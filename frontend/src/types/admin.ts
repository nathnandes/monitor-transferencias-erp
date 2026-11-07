

import type { DataISO } from "./api";
import type { Aba, Modulo, Papel } from "./auth";

export type { Papel };

export interface UsuarioAdmin {
  id: number;
  username: string;
  nome_exibicao: string;
  role: Papel;
  ativo: boolean;
  must_change_password: boolean;

  sessao_continua: boolean;

  perfil: PerfilResumo | null;
  last_login_at: DataISO | null;
  created_at: DataISO;
  updated_at: DataISO;
}

export interface PerfilResumo {
  id: number;
  nome: string;
}

export interface UsuarioAdminDetalhe extends UsuarioAdmin {

  modulos: Modulo[];
}

export interface PaginaUsuarios {
  total: number;
  pagina: number;
  tamanho_pagina: number;
  total_paginas: number;
  itens: UsuarioAdmin[];
}

export interface FiltrosUsuarios {

  busca: string;
  role: Papel | "";

  ativo: "true" | "false" | "";
}

export const FILTROS_USUARIOS_VAZIOS: FiltrosUsuarios = { busca: "", role: "", ativo: "" };

export interface CriarUsuarioEntrada {
  username: string;
  nome_exibicao: string;
  password_temporaria: string;
  role: Papel;
  modulos: Modulo[];
  sessao_continua: boolean;

  exigir_troca_senha: boolean;
  perfil_id: number | null;
}


export interface AtualizarUsuarioEntrada {
  nome_exibicao?: string;
  role?: Papel;
  ativo?: boolean;
  modulos?: Modulo[];
  sessao_continua?: boolean;

  perfil_id?: number | null;
}


export type ModuloDePerfil = Exclude<Modulo, "ADMINISTRACAO">;


export interface PerfilEntrada {
  nome: string;
  descricao: string | null;
  modulos: ModuloDePerfil[];
  abas: Aba[];

  tela_inicial: string | null;
}

export interface PerfilAdmin extends PerfilEntrada {
  id: number;

  usuarios: number;
  created_at: DataISO;
  updated_at: DataISO;
}
