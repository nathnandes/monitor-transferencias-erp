import { describe, expect, it } from "vitest";

import { pontoIndicadores } from "../../../test/factories";
import { INDICADORES, pontosDoCard, rotuloBalde, rotuloBaldeCompleto, semMovimento } from "./indicadoresEmpresa";

describe("rótulos dos baldes", () => {
  it("formata hora, dia e mês sem passar por Date (sem deslocamento de fuso)", () => {
    expect(rotuloBalde("2026-10-02T09", "hora")).toBe("9h");
    expect(rotuloBaldeCompleto("2026-10-02T09", "hora")).toBe("02/10/2026 9h");
    expect(rotuloBalde("2026-10-02", "dia")).toBe("02/10");
    expect(rotuloBaldeCompleto("2026-10-02", "dia")).toBe("02/10/2026");
    expect(rotuloBalde("2026-01", "mes")).toBe("jan/26");
    expect(rotuloBaldeCompleto("2026-12", "mes")).toBe("dez/2026");
  });
});

describe("pontosDoCard", () => {
  it("a linha é a média só dos baldes com valor", () => {
    const serie = [
      pontoIndicadores("2026-09-28", { taxa_entrada: 100 }),
      pontoIndicadores("2026-09-29"),
      pontoIndicadores("2026-09-30", { taxa_entrada: 50 }),
    ];

    const pontos = pontosDoCard(serie, "taxa_entrada", "dia");

    expect(pontos.map((p) => p.valor)).toEqual([100, null, 50]);
    expect(pontos.every((p) => p.media === 75)).toBe(true);
    expect(pontos[0]?.rotulo).toBe("28/09");
  });

  it("contagem zerada entra na média", () => {
    const serie = [pontoIndicadores("a", { enviadas: 3 }), pontoIndicadores("b")];
    expect(pontosDoCard(serie, "enviadas", "dia")[0]?.media).toBe(1.5);
  });
});

describe("definições", () => {
  it("formatam com no máximo uma casa decimal e a unidade certa", () => {
    const formato = Object.fromEntries(INDICADORES.map((d) => [d.campo, d.formatar]));
    expect(formato.enviadas?.(1234)).toBe("1.234");
    expect(formato.enviadas?.(1.55)).toBe("1,6");
    expect(formato.taxa_entrada?.(66.67)).toBe("66,7%");
    expect(formato.tempo_medio_entrada_horas?.(2.5)).toBe("2,5 h");
  });

  it("empresa sem movimento é detectada pelos totais", () => {
    expect(semMovimento(pontoIndicadores("total"))).toBe(true);
    expect(semMovimento(pontoIndicadores("total", { recebidas: 1 }))).toBe(false);
    expect(semMovimento(pontoIndicadores("total", { a_receber: 1 }))).toBe(false);
  });
});
