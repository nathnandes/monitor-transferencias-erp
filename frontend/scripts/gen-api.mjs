






import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const GERADOR = ["-y", "-p", "typescript@5.9.3", "-p", "openapi-typescript@7.13.0", "openapi-typescript"];
const ORIGEM = "openapi.json";
const DESTINO = "src/types/openapi.gen.ts";

const pasta = mkdtempSync(join(tmpdir(), "gen-api-"));
const temporario = join(pasta, "openapi.gen.ts");
try {

  execSync(`npx ${GERADOR.join(" ")} ${ORIGEM} -o "${temporario}"`, { stdio: "inherit" });
  const hash = createHash("sha256").update(readFileSync(ORIGEM, "utf8").replace(/\r\n/g, "\n")).digest("hex");
  const cabecalho =
    `// GERADO por "npm run gen:api" a partir de openapi.json. Nao edite a mao.\n` +
    `// openapi.json sha256: ${hash}\n\n`;
  writeFileSync(DESTINO, cabecalho + readFileSync(temporario, "utf8"));
  console.log(`tipos gerados em ${DESTINO}`);
} finally {
  rmSync(pasta, { recursive: true, force: true });
}
