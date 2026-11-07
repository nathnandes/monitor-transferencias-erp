import { describe, expect, it } from "vitest";

import { comparacaoDoPeriodo, descreverPeriodo, hojeNoFuso, intervaloDoPeriodo, somarDias } from "./periodo";


const HOJE = "2026-10-02";

function comparar(periodo: Parameters<typeof intervaloDoPeriodo>[0], hoje = HOJE, personalizado?: { inicio: string; fim: string }) {
  return comparacaoDoPeriodo(periodo, intervaloDoPeriodo(periodo, hoje, personalizado));
}

describe("intervalo do período", () => {
  it("hoje, ontem e mês até hoje", () => {
    expect(intervaloDoPeriodo("hoje", HOJE)).toEqual({ inicio: HOJE, fim: HOJE });
    expect(intervaloDoPeriodo("ontem", HOJE)).toEqual({ inicio: "2026-10-01", fim: "2026-10-01" });
    expect(intervaloDoPeriodo("mes", HOJE)).toEqual({ inicio: "2026-10-01", fim: HOJE });
  });

  it("tudo não recorta; personalizado só vale completo e na ordem", () => {
    expect(intervaloDoPeriodo("tudo", HOJE)).toBeNull();
    expect(intervaloDoPeriodo("personalizado", HOJE, { inicio: "2026-09-01" })).toBeNull();
    expect(intervaloDoPeriodo("personalizado", HOJE, { inicio: "2026-09-10", fim: "2026-09-01" })).toBeNull();
    expect(intervaloDoPeriodo("personalizado", HOJE, { inicio: "2026-09-01", fim: "2026-09-10" })).toEqual({
      inicio: "2026-09-01",
      fim: "2026-09-10",
    });
  });

  it("atravessa virada de mês e ano sem depender do fuso da máquina", () => {
    expect(somarDias("2026-03-01", -1)).toBe("2026-02-28");
    expect(somarDias("2027-01-01", -1)).toBe("2026-12-31");
  });

  it("hoje no fuso de exibição, não no UTC", () => {

    expect(hojeNoFuso(new Date("2026-10-02T02:00:00Z"), "America/Sao_Paulo")).toBe("2026-10-01");
  });
});

describe("comparação", () => {
  it("hoje: o mesmo dia da semana passada", () => {
    expect(comparar("hoje")).toEqual({ inicio: "2026-09-25", fim: "2026-09-25", rotulo: "sexta passada" });

    expect(comparar("hoje", "2026-10-03")?.rotulo).toBe("sábado passado");
    expect(comparar("hoje", "2026-10-04")?.rotulo).toBe("domingo passado");
  });

  it("ontem: o mesmo dia da semana anterior, com a data", () => {
    expect(comparar("ontem")).toEqual({ inicio: "2026-09-24", fim: "2026-09-24", rotulo: "quinta, 24/09" });
  });

  it("mês: os mesmos dias do mês anterior, cortados no último dia dele", () => {
    expect(comparar("mes")).toEqual({ inicio: "2026-09-01", fim: "2026-09-02", rotulo: "mesmo período de setembro" });

    expect(comparar("mes", "2026-03-31")).toMatchObject({ inicio: "2026-02-01", fim: "2026-02-28" });

    expect(comparar("mes", "2027-01-15")).toMatchObject({ inicio: "2026-12-01", fim: "2026-12-15", rotulo: "mesmo período de dezembro" });
  });

  it("personalizado: o mesmo número de dias logo antes", () => {
    expect(comparar("personalizado", HOJE, { inicio: "2026-09-08", fim: "2026-09-14" })).toEqual({
      inicio: "2026-09-01",
      fim: "2026-09-07",
      rotulo: "7 dias anteriores",
    });
    expect(comparar("personalizado", HOJE, { inicio: "2026-09-08", fim: "2026-09-08" })?.rotulo).toBe("dia anterior");
  });

  it("tudo: sem comparação", () => {
    expect(comparar("tudo")).toBeNull();
  });
});

describe("descrição do período", () => {
  it("textos curtos para subtítulos", () => {
    expect(descreverPeriodo("hoje", intervaloDoPeriodo("hoje", HOJE))).toBe("Hoje");
    expect(descreverPeriodo("mes", intervaloDoPeriodo("mes", HOJE))).toBe("Outubro até dia 2");
    expect(descreverPeriodo("tudo", null)).toBe("Todo o período");
    expect(descreverPeriodo("personalizado", { inicio: "2026-09-01", fim: "2026-09-10" })).toBe("01/09/2026 a 10/09/2026");
  });
});
