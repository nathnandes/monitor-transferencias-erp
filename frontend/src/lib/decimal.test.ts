import { describe, expect, it } from "vitest";

import { subtrairDecimais } from "./decimal";
import { opcoesDeStatus } from "./status";

describe("subtrairDecimais", () => {
  it("subtrai sem erro de ponto flutuante", () => {
    expect(subtrairDecimais("35.0000", "36.0000")).toBe("-1.0000");
    expect(subtrairDecimais("0.3", "0.1")).toBe("0.2");
    expect(subtrairDecimais("2.5", "2.5000")).toBe("0.0000");
    expect(subtrairDecimais("10", "9.125")).toBe("0.875");
    expect(subtrairDecimais("abc", "1")).toBeNull();
  });
});

describe("opcoesDeStatus", () => {
  it("mantém os conhecidos primeiro e acrescenta os vistos nos dados", () => {
    expect(opcoesDeStatus([])).toEqual(["PENDENTE", "PROCESSADA", "ERRO"]);
    expect(opcoesDeStatus(["processada", "CANCELADA", null, "ERRO"])).toEqual([
      "PENDENTE",
      "PROCESSADA",
      "ERRO",
      "CANCELADA",
    ]);
    expect(opcoesDeStatus([], "em_analise")).toContain("EM_ANALISE");
  });
});
