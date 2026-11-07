import { describe, expect, it } from "vitest";

import {
  chaveDia,
  formatarDataHora,
  formatarMoeda,
  formatarMoedaNumero,
  formatarMoedaCurta,
  formatarNumeroCurto,
  formatarQuantidade,
  tempoRelativo,
} from "./format";
import { normalizarStatus, tomDoStatus } from "./status";

const TZ = "America/Sao_Paulo";

describe("format", () => {
  it("formata quantidade decimal sem perder precisão", () => {
    expect(formatarQuantidade("36.0000")).toBe("36");
    expect(formatarQuantidade("2.5000")).toBe("2,5");
    expect(formatarQuantidade("1234567.0125")).toBe("1.234.567,0125");
    expect(formatarQuantidade(null)).toBe("—");
  });

  it("converte UTC para o fuso de exibição", () => {

    expect(formatarDataHora("2026-09-26T02:30:00Z", TZ)).toBe("25/09/2026, 23:30");
    expect(chaveDia("2026-09-26T02:30:00Z", TZ)).toBe("2026-09-25");
    expect(formatarDataHora(null)).toBe("—");
  });

  it("descreve tempo relativo", () => {
    const agora = new Date("2026-09-26T12:00:00Z");
    expect(tempoRelativo("2026-09-26T11:55:00Z", agora)).toBe("há 5 min");
    expect(tempoRelativo("2026-09-26T09:00:00Z", agora)).toBe("há 3 h");
    expect(tempoRelativo("2026-09-24T12:00:00Z", agora)).toBe("há 2 dias");
  });
});

describe("status", () => {
  it("normaliza e classifica status de transferência", () => {
    expect(normalizarStatus(" pendente ")).toBe("PENDENTE");
    expect(normalizarStatus(null)).toBe("SEM STATUS");
    expect(tomDoStatus("processada")).toBe("bom");
    expect(tomDoStatus("ERRO")).toBe("critico");
    expect(tomDoStatus("CANCELADA")).toBe("neutro");
  });
});

describe("formatarMoeda", () => {
  it("arredonda para 2 casas, meio para cima, com milhar pt-BR", () => {
    expect(formatarMoeda("1234.565")).toBe("R$ 1.234,57");
    expect(formatarMoeda("12.900000")).toBe("R$ 12,90");
    expect(formatarMoeda("0.004")).toBe("R$ 0,00");
    expect(formatarMoeda("7")).toBe("R$ 7,00");
    expect(formatarMoeda("-15.5")).toBe("-R$ 15,50");
  });

  it("negativo que arredonda para zero não leva sinal; vazio vira traço", () => {
    expect(formatarMoeda("-0.001")).toBe("R$ 0,00");
    expect(formatarMoeda(null)).toBe(formatarQuantidade(null));
  });
});

describe("formatarMoedaCurta", () => {
  it("abrevia em mil e mi, como os rótulos dos gráficos", () => {
    expect(formatarMoedaCurta(950.4)).toBe("R$ 950");
    expect(formatarMoedaCurta(281_400)).toBe("R$ 281 mil");
    expect(formatarMoedaCurta(2_574_000)).toBe("R$ 2,57 mi");
    expect(formatarMoedaCurta(-12_500)).toBe("-R$ 13 mil");
  });
});

describe("formatarNumeroCurto", () => {
  it("mantém números pequenos inteiros e abrevia os grandes", () => {
    expect(formatarNumeroCurto(9_876)).toBe("9.876");
    expect(formatarNumeroCurto(12_430)).toBe("12,4 mil");
    expect(formatarNumeroCurto(2_102_713)).toBe("2,1 mi");
  });
});

describe("formatarMoedaNumero", () => {
  it("formata a soma feita em number sem passar por notação científica", () => {
    expect(formatarMoedaNumero(1234.5)).toBe("R$ 1.234,50");
    expect(formatarMoedaNumero(-0.0000001)).toBe("R$ 0,00");
    expect(formatarMoedaNumero(-12.345)).toBe("-R$ 12,35");
    expect(formatarMoedaNumero(Number.NaN)).toBe(formatarMoeda(null));
  });
});
