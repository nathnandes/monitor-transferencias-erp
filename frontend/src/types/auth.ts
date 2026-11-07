

import type { components } from "./openapi.gen";


export type Modulo = components["schemas"]["PermissoesUsuario"]["modulos"][number];


export type Aba = NonNullable<components["schemas"]["PermissoesUsuario"]["abas"]>[number];


export type Papel = components["schemas"]["UsuarioAutenticado"]["role"];

export interface Usuario {
  id: number;
  username: string;
  nome_exibicao: string;
  role: Papel;
  ativo: boolean;
  must_change_password: boolean;

  sessao_continua: boolean;
}

export interface TokenAcesso {
  access_token: string;
  token_type: "bearer";

  expires_in: number;
  user: Usuario;
}

export interface PermissoesUsuario {
  modulos: Modulo[];

  abas?: Aba[] | null;

  tela_inicial?: string | null;
}


export interface ErroPoliticaSenha {
  mensagem: string;
  problemas: string[];
}
