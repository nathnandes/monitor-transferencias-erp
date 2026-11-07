

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

function paraEscalado(valor: string, casas: number): bigint | null {
  const m = DECIMAL.exec(valor.trim());
  if (!m) return null;
  const [, sinal = "", inteiro = "0", fracao = ""] = m;
  const n = BigInt(inteiro + fracao.padEnd(casas, "0"));
  return sinal ? -n : n;
}

function casasDecimais(valor: string): number {
  return valor.trim().split(".")[1]?.length ?? 0;
}


export function subtrairDecimais(a: string, b: string): string | null {
  const casas = Math.max(casasDecimais(a), casasDecimais(b));
  const x = paraEscalado(a, casas);
  const y = paraEscalado(b, casas);
  if (x === null || y === null) return null;

  const r = x - y;
  const negativo = r < 0n;
  const digitos = (negativo ? -r : r).toString().padStart(casas + 1, "0");
  const inteiro = casas ? digitos.slice(0, -casas) : digitos;
  const fracao = casas ? digitos.slice(-casas) : "";
  return `${negativo ? "-" : ""}${inteiro}${fracao ? `.${fracao}` : ""}`;
}
