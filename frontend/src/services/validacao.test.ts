import { afterEach, describe, expect, it, vi } from "vitest";

import { respostaJson } from "../test/factories";
import { ApiError } from "./apiClient";
import { getPainelControle } from "./controleTransferenciasService";
import { getEstoque, getLivroEstoque } from "./estoqueService";
import { getTransferencias } from "./transferenciasService";
import { inteiro, lista, objeto, ouNulo, texto, validarFormato } from "./validacao";

afterEach(() => vi.unstubAllGlobals());

describe("validarFormato", () => {
  it("devolve o dado quando os campos conferem", () => {
    const dados = { total: 2, itens: [], filtro: { empresa: null }, gerado_em: null };
    const campos = { total: inteiro, itens: lista, filtro: objeto, gerado_em: ouNulo(texto) };
    expect(validarFormato(dados, "A lista", campos)).toBe(dados);
  });

  it("lista cada campo fora do contrato num ApiError de resposta", () => {
    const erro = (() => {
      try {
        validarFormato({ total: "2" }, "A lista", { total: inteiro, itens: lista });
      } catch (e) {
        return e as ApiError;
      }
    })();
    expect(erro).toBeInstanceOf(ApiError);
    expect(erro?.tipo).toBe("resposta_invalida");
    expect(erro?.message).toMatch(/A lista veio em formato inesperado \(total, itens\)/);
  });
});

describe("services que alimentam cálculo validam a resposta", () => {
  it.each([
    ["estoque", () => getEstoque({})],
    ["livro", () => getLivroEstoque({})],
    ["controle", () => getPainelControle({})],
    ["transferências", () => getTransferencias({})],
  ])("%s: corpo fora do contrato vira erro, e não tela com undefined", async (_nome, chamar) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respostaJson({ inesperado: true })));

    const erro = await chamar().catch((e: unknown) => e);

    expect(erro).toBeInstanceOf(ApiError);
    expect((erro as ApiError).tipo).toBe("resposta_invalida");
  });
});
