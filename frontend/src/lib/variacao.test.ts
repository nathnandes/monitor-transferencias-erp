import { describe, expect, it } from "vitest";

import { calcularVariacao } from "./variacao";

describe("calcularVariacao", () => {
  it("seta, percentual e frase completa", () => {
    expect(calcularVariacao(12, 10, "sexta passada", "subir")).toEqual({
      texto: "▲ 20%",
      tom: "bom",
      descricao: "20% a mais que sexta passada (10).",
    });
    expect(calcularVariacao(8, 10, "sexta passada", "subir")).toMatchObject({ texto: "▼ 20%", tom: "critico" });
  });

  it("o tom segue o sentido em que o número melhora", () => {
    expect(calcularVariacao(12, 10, "x", "descer").tom).toBe("critico");
    expect(calcularVariacao(8, 10, "x", "descer").tom).toBe("bom");
    expect(calcularVariacao(12, 10, "x", "neutro").tom).toBe("neutro");
  });

  it("igual, base zero e variação menor que 1%", () => {
    expect(calcularVariacao(5, 5, "x", "subir")).toMatchObject({ texto: "= igual", tom: "neutro" });
    expect(calcularVariacao(0, 0, "x", "subir").texto).toBe("= igual");
    expect(calcularVariacao(3, 0, "x", "subir")).toMatchObject({ texto: "▲ novo", tom: "bom" });
    expect(calcularVariacao(1001, 1000, "x", "subir").texto).toBe("▲ < 1%");
  });
});
