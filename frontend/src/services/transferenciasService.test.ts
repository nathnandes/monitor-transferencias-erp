import { afterEach, describe, expect, it, vi } from "vitest";

import { pagina, respostaJson, transferencia } from "../test/factories";
import { coletarTransferencias, getTransferencia, getTransferencias } from "./transferenciasService";

function mockFetch(...respostas: Response[]) {
  const fn = vi.fn();
  for (const r of respostas) fn.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fn);
  return fn;
}

const urlChamada = (fn: ReturnType<typeof vi.fn>, i = 0) => String(fn.mock.calls[i]?.[0]);

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("transferenciasService", () => {
  it("getTransferencias envia filtros e paginação com os nomes da API", async () => {
    const fn = mockFetch(respostaJson(pagina([])));
    await getTransferencias(
      { empresa_origem: "01", empresa_destino: "", status: "ERRO", data_inicial: "2026-09-01", data_final: "2026-09-26" },
      3,
      20,
    );
    const url = new URL(urlChamada(fn), "http://localhost");
    expect(url.pathname).toBe("/api/v1/transferencias");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      empresa_origem: "01",
      status: "ERRO",
      data_inicial: "2026-09-01",
      data_final: "2026-09-26",
      pagina: "3",
      tamanho_pagina: "20",
    });
  });

  it("getTransferencia usa o id no caminho", async () => {
    const fn = mockFetch(respostaJson({}));
    await getTransferencia(42);
    expect(urlChamada(fn)).toBe("/api/v1/transferencias/42");
  });

  it("coletarTransferencias percorre todas as páginas com tamanho máximo", async () => {
    const fn = mockFetch(
      respostaJson(pagina([transferencia({ id: 1 })], { total: 2, total_paginas: 2, tamanho_pagina: 100 })),
      respostaJson(pagina([transferencia({ id: 2 })], { total: 2, total_paginas: 2, pagina: 2, tamanho_pagina: 100 })),
    );
    const coleta = await coletarTransferencias({ status: "PENDENTE" });
    expect(coleta.itens.map((t) => t.id)).toEqual([1, 2]);
    expect(coleta.truncado).toBe(false);
    expect(urlChamada(fn, 1)).toContain("pagina=2&tamanho_pagina=100");
  });

  it("coletarTransferencias respeita o limite de páginas e sinaliza truncado", async () => {
    const fn = mockFetch(respostaJson(pagina([transferencia({ id: 1 })], { total: 300, total_paginas: 3 })));
    const coleta = await coletarTransferencias({}, 1);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(coleta).toMatchObject({ total: 300, truncado: true });
  });
});
