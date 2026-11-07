import { afterEach, describe, expect, it, vi } from "vitest";

import { respostaJson } from "../test/factories";
import {
  ativarUsuario,
  atualizarUsuario,
  criarUsuario,
  desativarUsuario,
  listarUsuarios,
  redefinirSenha,
} from "./adminUsuariosService";

function mockFetch() {
  const fn = vi.fn(async () => respostaJson({}));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const chamada = (fn: ReturnType<typeof mockFetch>) => {
  const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
  return { url, metodo: init.method, corpo: init.body ? JSON.parse(String(init.body)) : undefined };
};

afterEach(() => vi.unstubAllGlobals());

describe("adminUsuariosService", () => {
  it("lista com filtros na query, omitindo os vazios e limitando o tamanho", async () => {
    const fn = mockFetch();
    await listarUsuarios({ busca: "  joao ", role: "", ativo: "false" }, 2, 500);
    expect(chamada(fn).url).toBe("/api/v1/admin/users?busca=joao&ativo=false&pagina=2&tamanho_pagina=100");
  });

  it("cria e redefine senha com a senha só no corpo do POST", async () => {
    let fn = mockFetch();
    await criarUsuario({ username: "a.b", nome_exibicao: "A", password_temporaria: "Segredo-123x", role: "OPERADOR", modulos: [], sessao_continua: false, exigir_troca_senha: false, perfil_id: null });
    expect(chamada(fn)).toMatchObject({ url: "/api/v1/admin/users", metodo: "POST" });
    expect(chamada(fn).url).not.toContain("Segredo");
    expect(chamada(fn).corpo.password_temporaria).toBe("Segredo-123x");

    vi.unstubAllGlobals();
    fn = mockFetch();
    await redefinirSenha(7, "Segredo-123x", true);
    expect(chamada(fn)).toEqual({
      url: "/api/v1/admin/users/7/reset-password",
      metodo: "POST",
      corpo: { password_temporaria: "Segredo-123x", exigir_troca_senha: true },
    });
  });

  it("edita com PATCH e ativa/desativa com POST", async () => {
    let fn = mockFetch();
    await atualizarUsuario(7, { nome_exibicao: "Novo" });
    expect(chamada(fn)).toEqual({ url: "/api/v1/admin/users/7", metodo: "PATCH", corpo: { nome_exibicao: "Novo" } });

    vi.unstubAllGlobals();
    fn = mockFetch();
    await ativarUsuario(7);
    expect(chamada(fn)).toMatchObject({ url: "/api/v1/admin/users/7/activate", metodo: "POST" });

    vi.unstubAllGlobals();
    fn = mockFetch();
    await desativarUsuario(7);
    expect(chamada(fn)).toMatchObject({ url: "/api/v1/admin/users/7/deactivate", metodo: "POST" });
  });
});
