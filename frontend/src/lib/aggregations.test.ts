import { describe, expect, it } from "vitest";

import { empresa, transferencia } from "../test/factories";
import {
  agruparPorSemana,
  contarPorDia,
  contarPorEmpresa,
  ehDadoSimulado,
  inicioDaSemana,
  ordenarSeveridades,
  serieDiaria,
  serieTemporal,
  statusDoResumo,
} from "./aggregations";

const TZ = "America/Sao_Paulo";

describe("aggregations", () => {
  it("monta o gráfico de status a partir dos totais do resumo", () => {
    expect(statusDoResumo({ total: 36, processadas: 26, pendentes: 5, com_erro: 5 })).toEqual([
      { status: "PROCESSADA", total: 26 },
      { status: "PENDENTE", total: 5 },
      { status: "ERRO", total: 5 },
    ]);
  });

  it("agrupa em OUTROS o que o resumo conta no total mas não nos três status", () => {
    expect(statusDoResumo({ total: 10, processadas: 5, pendentes: 2, com_erro: 1 }).at(-1)).toEqual({
      status: "OUTROS",
      total: 2,
    });
  });

  it("status sem transferências é lista vazia (EmptyState)", () => {
    expect(statusDoResumo({ total: 0, processadas: 0, pendentes: 0, com_erro: 0 })).toEqual([]);
  });

  it("conta saídas e entradas por empresa", () => {
    const itens = [
      transferencia({ empresa_origem: empresa("01"), empresa_destino: empresa("02") }),
      transferencia({ empresa_origem: empresa("01"), empresa_destino: empresa("03") }),
      transferencia({ empresa_origem: empresa("02"), empresa_destino: empresa("01") }),
    ];
    expect(contarPorEmpresa(itens)).toEqual([
      { codigo: "01", nome: "Empresa 01", saidas: 2, entradas: 1 },
      { codigo: "02", nome: "Empresa 02", saidas: 1, entradas: 1 },
      { codigo: "03", nome: "Empresa 03", saidas: 0, entradas: 1 },
    ]);
  });

  it("conta por dia no fuso local e preenche dias sem movimento", () => {
    const itens = [
      transferencia({ data_criacao: "2026-09-20T15:00:00Z" }),
      transferencia({ data_criacao: "2026-09-23T02:00:00Z" }),
      transferencia({ data_criacao: "2026-09-20T18:00:00Z" }),
      transferencia({ data_criacao: null }),
    ];
    expect(contarPorDia(itens, TZ)).toEqual([
      { dia: "2026-09-20", total: 2 },
      { dia: "2026-09-21", total: 0 },
      { dia: "2026-09-22", total: 1 },
    ]);
    expect(contarPorDia([], TZ)).toEqual([]);
  });

  it("rotula a série diária", () => {
    expect(serieDiaria([{ dia: "2026-09-20", total: 3 }])).toEqual([
      { chave: "2026-09-20", rotulo: "20/09", rotuloCompleto: "20/09/2026", total: 3 },
    ]);
  });

  it("encontra a segunda-feira da semana", () => {
    expect(inicioDaSemana("2026-09-21")).toBe("2026-09-21");
    expect(inicioDaSemana("2026-09-26")).toBe("2026-09-21");
    expect(inicioDaSemana("2026-09-27")).toBe("2026-09-21");
    expect(inicioDaSemana("2026-10-01")).toBe("2026-09-28");
  });

  it("soma os dias por semana (segunda a domingo)", () => {
    const dias = [
      { dia: "2026-09-19", total: 1 },
      { dia: "2026-09-20", total: 2 },
      { dia: "2026-09-21", total: 0 },
      { dia: "2026-09-26", total: 4 },
    ];
    expect(agruparPorSemana(dias)).toEqual([
      { chave: "2026-09-14", rotulo: "14/09", rotuloCompleto: "Semana de 14/09/2026 a 20/09/2026", total: 3 },
      { chave: "2026-09-21", rotulo: "21/09", rotuloCompleto: "Semana de 21/09/2026 a 27/09/2026", total: 4 },
    ]);
    expect(serieTemporal(dias, "semana")).toHaveLength(2);
    expect(serieTemporal(dias, "dia")).toHaveLength(4);
    expect(agruparPorSemana([])).toEqual([]);
  });

  it("ordena severidades de INFO a CRITICAL", () => {
    expect(ordenarSeveridades({ CRITICAL: 3, INFO: 4, ERROR: 7, WARNING: 7 }).map((s) => s.severidade)).toEqual([
      "INFO",
      "WARNING",
      "ERROR",
      "CRITICAL",
    ]);
  });

  it("reconhece o marcador do seed", () => {
    expect(ehDadoSimulado("DEMO-TRF-0001")).toBe(true);
    expect(ehDadoSimulado("12345")).toBe(false);
    expect(ehDadoSimulado(null)).toBe(false);
  });
});
