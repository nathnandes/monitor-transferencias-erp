import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";




describe("openapi.gen.ts", () => {
  it("foi gerado do openapi.json atual (senão: npm run gen:api)", () => {
    const contrato = readFileSync("openapi.json", "utf8").replace(/\r\n/g, "\n");
    const esperado = createHash("sha256").update(contrato).digest("hex");
    const gerado = readFileSync("src/types/openapi.gen.ts", "utf8");
    expect(gerado).toContain(`openapi.json sha256: ${esperado}`);
  });
});
