import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { describe, expect, it } from "vitest";


const TRANSVERSAIS = new Set(["auth"]);
const SRC = resolve(__dirname, "..");
const FEATURES = join(SRC, "features");

function arquivos(pasta: string): string[] {
  return readdirSync(pasta).flatMap((nome) => {
    const caminho = join(pasta, nome);
    if (statSync(caminho).isDirectory()) return arquivos(caminho);
    return /\.(ts|tsx)$/.test(nome) ? [caminho] : [];
  });
}

function featureDe(caminho: string): string | null {
  const rel = relative(FEATURES, caminho);
  return rel.startsWith("..") ? null : rel.split(sep)[0]!;
}

describe("fronteiras do frontend", () => {
  it("nenhuma feature importa arquivos de outra feature", () => {
    const violacoes: string[] = [];
    for (const arquivo of arquivos(FEATURES)) {
      const dona = featureDe(arquivo);
      for (const [, alvo] of readFileSync(arquivo, "utf8").matchAll(/from "(\.{1,2}\/[^"]+)"/g)) {
        const outra = featureDe(resolve(dirname(arquivo), alvo!));
        if (outra && outra !== dona && !TRANSVERSAIS.has(outra)) violacoes.push(`${relative(SRC, arquivo)} -> ${alvo}`);
      }
    }
    expect(violacoes).toEqual([]);
  });
});
