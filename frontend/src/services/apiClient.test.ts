import { afterEach, describe, expect, it, vi } from "vitest";

import { respostaJson } from "../test/factories";
import { ApiError, baixarArquivo, configurarAutenticacao, deleteJson, getJson, montarQuery, postJson } from "./apiClient";

function mockFetch(...respostas: Array<Response | Error>) {
  const fn = vi.fn();
  for (const r of respostas) {
    if (r instanceof Error) fn.mockRejectedValueOnce(r);
    else fn.mockResolvedValueOnce(r);
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("montarQuery", () => {
  it("ignora valores vazios, nulos e indefinidos", () => {
    expect(montarQuery({ a: "", b: null, c: undefined })).toBe("");
    expect(montarQuery({ empresa_origem: "01", status: "", pagina: 2 })).toBe("?empresa_origem=01&pagina=2");
  });

  it("repete a chave para cada item de uma lista", () => {
    expect(montarQuery({ marca: ["TIGRE", "3M"], mais_de: 1 })).toBe("?marca=TIGRE&marca=3M&mais_de=1");
    expect(montarQuery({ marca: [] })).toBe("");
  });
});

describe("getJson", () => {
  it("chama a URL relativa em dev (proxy do Vite) e devolve o JSON", async () => {
    const fn = mockFetch(respostaJson({ ok: true }));
    await expect(getJson("/api/v1/x", { params: { a: 1 } })).resolves.toEqual({ ok: true });
    expect(fn.mock.calls[0]?.[0]).toBe("/api/v1/x?a=1");
    expect(fn.mock.calls[0]?.[1]).toMatchObject({ headers: { Accept: "application/json" } });
  });

  it("usa o detail string do FastAPI como mensagem", async () => {
    mockFetch(respostaJson({ detail: "Transferência 999 não encontrada." }, 404));
    const erro = (await getJson("/x").catch((e: unknown) => e)) as ApiError;
    expect(erro).toBeInstanceOf(ApiError);
    expect(erro).toMatchObject({ tipo: "http", status: 404, message: "Transferência 999 não encontrada." });
  });

  it("junta as mensagens de validação (422 em lista)", async () => {
    mockFetch(respostaJson({ detail: [{ msg: "campo a" }, { msg: "campo b" }] }, 422));
    await expect(getJson("/x")).rejects.toThrow("campo a; campo b");
  });

  it("usa mensagem genérica quando o corpo de erro não é JSON", async () => {
    mockFetch(new Response("<html>Bad Gateway</html>", { status: 502 }));
    await expect(getJson("/x")).rejects.toThrow("HTTP 502");
  });

  it("acusa resposta 200 que não é JSON", async () => {
    mockFetch(new Response("<html>index</html>", { status: 200 }));
    await expect(getJson("/x")).rejects.toMatchObject({ tipo: "resposta_invalida" });
  });

  it("traduz falha de rede em mensagem clara", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    const erro = (await getJson("/x").catch((e: unknown) => e)) as ApiError;
    expect(erro).toMatchObject({ tipo: "rede", status: null });
    expect(erro.message).toMatch(/backend está em execução/);
  });

  it("aborta e informa quando a API não responde no prazo", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_, rejeitar) => {
            init.signal?.addEventListener("abort", () => rejeitar(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    const promessa = getJson("/x", { timeoutMs: 2000 }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(2000);
    const erro = (await promessa) as ApiError;
    expect(erro).toMatchObject({ tipo: "timeout" });
    expect(erro.message).toContain("2 s");
  });

  it("repassa o cancelamento do chamador sem virar ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_, rejeitar) => {
            init.signal?.addEventListener("abort", () => rejeitar(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    const controle = new AbortController();
    const promessa = getJson("/x", { signal: controle.signal });
    controle.abort();
    const erro = await promessa.catch((e: unknown) => e);
    expect(erro).not.toBeInstanceOf(ApiError);
    expect((erro as DOMException).name).toBe("AbortError");
  });
});

describe("deleteJson", () => {
  it("manda DELETE sem corpo e devolve undefined no 204", async () => {
    const fn = mockFetch(new Response(null, { status: 204 }));
    await expect(deleteJson("/api/v1/x/1")).resolves.toBeUndefined();
    const init = fn.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });
});

describe("autenticação", () => {
  const cabecalhos = (fn: ReturnType<typeof vi.fn>, i = 0) =>
    (fn.mock.calls[i]?.[1] as RequestInit).headers as Record<string, string>;

  it("sem sessão, não envia Authorization", async () => {
    const fn = mockFetch(respostaJson({}));
    await getJson("/x");
    expect(cabecalhos(fn)).not.toHaveProperty("Authorization");
  });

  it("com sessão, envia Authorization: Bearer <token>", async () => {
    const desfazer = configurarAutenticacao({ obterToken: () => "abc", aoRecusarToken: vi.fn() });
    const fn = mockFetch(respostaJson({}));
    await getJson("/x");
    expect(cabecalhos(fn).Authorization).toBe("Bearer abc");
    desfazer();
  });

  it("401 numa requisição autenticada avisa a sessão com o token enviado", async () => {
    const aoRecusarToken = vi.fn();
    const desfazer = configurarAutenticacao({ obterToken: () => "abc", aoRecusarToken });
    mockFetch(respostaJson({ detail: "Não autenticado." }, 401));
    await expect(getJson("/x")).rejects.toMatchObject({ status: 401 });
    expect(aoRecusarToken).toHaveBeenCalledWith("abc");
    desfazer();
  });

  it("403 não encerra a sessão", async () => {
    const aoRecusarToken = vi.fn();
    const desfazer = configurarAutenticacao({ obterToken: () => "abc", aoRecusarToken });
    mockFetch(respostaJson({ detail: "Sem permissão para acessar este recurso." }, 403));
    await expect(getJson("/x")).rejects.toMatchObject({ status: 403 });
    expect(aoRecusarToken).not.toHaveBeenCalled();
    desfazer();
  });

  it("rota pública (login): sem Authorization e 401 não encerra sessão", async () => {
    const aoRecusarToken = vi.fn();
    const desfazer = configurarAutenticacao({ obterToken: () => "abc", aoRecusarToken });
    const fn = mockFetch(respostaJson({ detail: "Usuário ou senha inválidos." }, 401));
    await expect(postJson("/login", { username: "u", password: "p" }, { autenticado: false })).rejects.toThrow(
      "Usuário ou senha inválidos.",
    );
    expect(cabecalhos(fn)).not.toHaveProperty("Authorization");
    expect(aoRecusarToken).not.toHaveBeenCalled();
    desfazer();
  });

  it("postJson envia JSON no corpo (nunca na URL) e aceita 204", async () => {
    const fn = mockFetch(new Response(null, { status: 204 }));
    await expect(postJson("/api/v1/auth/logout", undefined, { token: "t" })).resolves.toBeUndefined();
    const [url, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/logout");
    expect(init.method).toBe("POST");
    expect(init.body).toBe("{}");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t");
  });

  it("422 da política de senha: usa a mensagem e guarda o corpo", async () => {
    const corpo = { detail: { mensagem: "Nova senha não atende à política.", problemas: ["ao menos um numero"] } };
    mockFetch(respostaJson(corpo, 422));
    const erro = (await postJson("/x", {}).catch((e: unknown) => e)) as ApiError;
    expect(erro.message).toBe("Nova senha não atende à política.");
    expect(erro.corpo).toEqual(corpo);
  });
});

describe("baixarArquivo", () => {
  it("baixa com o token, usa o nome do Content-Disposition e devolve o total", async () => {
    const desfazer = configurarAutenticacao({ obterToken: () => "tok", aoRecusarToken: () => {} });
    const fn = mockFetch(
      new Response("﻿Nota;Origem\r\n", {
        status: 200,
        headers: {
          "Content-Type": "text/csv; charset=utf-8",
          "Content-Disposition": 'attachment; filename="transferencias_20261014_1500.csv"',
          "X-Total-Registros": "1",
        },
      }),
    );
    const criar = vi.fn(() => "blob:x");
    const revogar = vi.fn();

    const original = { criar: URL.createObjectURL, revogar: URL.revokeObjectURL };
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: revogar });
    const clique = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const arquivo = await baixarArquivo("/api/v1/transferencias/exportar", { status: "PENDENTE" });

    expect(arquivo).toEqual({ nome: "transferencias_20261014_1500.csv", total: 1 });
    expect(fn.mock.calls[0]?.[0]).toBe("/api/v1/transferencias/exportar?status=PENDENTE");
    expect(fn.mock.calls[0]?.[1]).toMatchObject({ headers: { Authorization: "Bearer tok" } });
    expect(clique).toHaveBeenCalledOnce();
    expect(revogar).toHaveBeenCalledWith("blob:x");
    clique.mockRestore();
    Object.assign(URL, { createObjectURL: original.criar, revokeObjectURL: original.revogar });
    desfazer();
  });

  it("erro da API vira ApiError, como nas consultas", async () => {
    mockFetch(respostaJson({ detail: "Empresa 77 não encontrada." }, 404));
    await expect(baixarArquivo("/api/v1/estoque/exportar", { empresa: "77" })).rejects.toMatchObject({
      tipo: "http",
      status: 404,
      message: "Empresa 77 não encontrada.",
    });
  });
});
