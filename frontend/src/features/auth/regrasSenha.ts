

export const SENHA_MIN = 4;
export const SENHA_MAX = 128;

export interface RegraSenha {
  id: string;
  texto: string;
  atende: (nova: string, atual: string) => boolean;
}


const tamanho = (s: string) => Array.from(s).length;


export const REGRAS_POLITICA: RegraSenha[] = [
  {
    id: "tamanho",
    texto: `De ${SENHA_MIN} a ${SENHA_MAX} caracteres`,
    atende: (n) => tamanho(n) >= SENHA_MIN && tamanho(n) <= SENHA_MAX,
  },
];


export const REGRAS_SENHA: RegraSenha[] = [
  ...REGRAS_POLITICA,
  { id: "diferente", texto: "Diferente da senha atual", atende: (n, a) => n.length > 0 && n !== a },
];

export function senhaAtendePolitica(nova: string, atual: string): boolean {
  return REGRAS_SENHA.every((r) => r.atende(nova, atual));
}

export function senhaTemporariaValida(senha: string): boolean {
  return REGRAS_POLITICA.every((r) => r.atende(senha, ""));
}
