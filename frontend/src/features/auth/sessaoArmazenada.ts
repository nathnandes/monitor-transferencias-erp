

const CHAVE = "erp.sessao";

export interface SessaoArmazenada {
  token: string;

  expiraEm: number;
}

export function lerSessao(agora = Date.now()): SessaoArmazenada | null {
  try {
    const bruto = window.sessionStorage.getItem(CHAVE);
    if (!bruto) return null;
    const dados = JSON.parse(bruto) as Partial<SessaoArmazenada>;
    if (typeof dados.token !== "string" || !dados.token || typeof dados.expiraEm !== "number") {
      limparSessao();
      return null;
    }
    if (dados.expiraEm <= agora) {
      limparSessao();
      return null;
    }
    return { token: dados.token, expiraEm: dados.expiraEm };
  } catch {
    return null;
  }
}

export function salvarSessao(sessao: SessaoArmazenada): void {
  try {
    window.sessionStorage.setItem(CHAVE, JSON.stringify(sessao));
  } catch {

  }
}

export function limparSessao(): void {
  try {
    window.sessionStorage.removeItem(CHAVE);
  } catch {

  }
}


export function calcularExpiracao(expiresIn: number, agora = Date.now()): number {
  const FOLGA_MS = 15_000;
  return agora + Math.max(0, expiresIn * 1000 - FOLGA_MS);
}
