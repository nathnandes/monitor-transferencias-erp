import { afterEach, describe, expect, it, vi } from "vitest";

import { respostaJson, resumo } from "../test/factories";
import { ApiError } from "./apiClient";
import { CAMINHO_RESUMO, getResumoDashboard, resumoVazio, validarResumo } from "./dashboardService";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getResumoDashboard", () => {
  it("chama GET /api/v1/dashboard/resumo e devolve o resumo", async () => {
    const fn = vi.fn().mockResolvedValue(respostaJson(resumo()));
    vi.stubGlobal("fetch", fn);
    await expect(getResumoDashboard()).resolves.toEqual(resumo());
    expect(fn.mock.calls[0]?.[0]).toBe(CAMINHO_RESUMO);
  });

  it("aceita ultima_sincronizacao nula", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respostaJson(resumo({ ultima_sincronizacao: null }))));
    await expect(getResumoDashboard()).resolves.toMatchObject({ ultima_sincronizacao: null });
  });

  it("rejeita resposta fora do contrato em vez de exibir dado errado", async () => {
    const quebrado = { ...resumo(), transferencias: { total: "36" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respostaJson(quebrado)));
    const erro = (await getResumoDashboard().catch((e: unknown) => e)) as ApiError;
    expect(erro).toBeInstanceOf(ApiError);
    expect(erro.tipo).toBe("resposta_invalida");
    expect(erro.message).toContain("transferencias.total");
    expect(erro.message).toContain("transferencias.com_erro");
  });
});

describe("validarResumo", () => {
  it("lista cada campo ausente", () => {
    expect(() => validarResumo({})).toThrow(/gerado_em, transferencias, empresas_ativas/);
    expect(() => validarResumo(null)).toThrow(/não é um objeto/);
  });

  it("exige as 4 severidades em eventos_por_severidade", () => {
    const { CRITICAL: _, ...semCritical } = resumo().eventos_por_severidade;
    expect(() => validarResumo({ ...resumo(), eventos_por_severidade: semCritical })).toThrow(/eventos_por_severidade/);
    expect(validarResumo(resumo()).eventos_por_severidade.CRITICAL).toBeTypeOf("number");
  });
});

describe("resumoVazio", () => {
  it("só é vazio sem transferências, empresas e sincronização", () => {
    const vazio = resumo({
      transferencias: { total: 0, processadas: 0, pendentes: 0, com_erro: 0 },
      empresas_ativas: 0,
      ultima_sincronizacao: null,
    });
    expect(resumoVazio(vazio)).toBe(true);
    expect(resumoVazio({ ...vazio, empresas_ativas: 1 })).toBe(false);
    expect(resumoVazio(resumo())).toBe(false);
  });
});
