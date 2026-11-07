import { afterEach, describe, expect, it } from "vitest";

import { calcularExpiracao, lerSessao, limparSessao, salvarSessao } from "./sessaoArmazenada";

afterEach(() => window.sessionStorage.clear());

describe("sessaoArmazenada", () => {
  it("guarda só token e expiração, em sessionStorage (não em localStorage)", () => {
    salvarSessao({ token: "t1", expiraEm: Date.now() + 60_000 });
    expect(lerSessao()).toMatchObject({ token: "t1" });
    expect(Object.keys(JSON.parse(window.sessionStorage.getItem("erp.sessao")!))).toEqual(["token", "expiraEm"]);
    expect(window.localStorage.length).toBe(0);
  });

  it("descarta sessão expirada", () => {
    salvarSessao({ token: "t1", expiraEm: Date.now() - 1 });
    expect(lerSessao()).toBeNull();
    expect(window.sessionStorage.getItem("erp.sessao")).toBeNull();
  });

  it("descarta conteúdo inválido", () => {
    window.sessionStorage.setItem("erp.sessao", "{não é json");
    expect(lerSessao()).toBeNull();
    window.sessionStorage.setItem("erp.sessao", JSON.stringify({ token: 1 }));
    expect(lerSessao()).toBeNull();
  });

  it("limparSessao remove o token", () => {
    salvarSessao({ token: "t1", expiraEm: Date.now() + 60_000 });
    limparSessao();
    expect(lerSessao()).toBeNull();
  });

  it("expiração vem de expires_in, com folga", () => {
    expect(calcularExpiracao(1800, 0)).toBe(1800_000 - 15_000);
    expect(calcularExpiracao(5, 0)).toBe(0);
  });
});
