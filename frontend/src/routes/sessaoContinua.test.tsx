

import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../features/auth/AuthProvider";
import { lerSessao, salvarSessao } from "../features/auth/sessaoArmazenada";
import { TITULO_DASHBOARD } from "../features/dashboard/DashboardPage";
import { resumo, respostaJson } from "../test/factories";
import { LocalAtual, tokenTeste, usuarioTeste } from "../test/sessao";
import { AppRoutes } from "./AppRoutes";

const RENOVAR = "/api/v1/auth/renew";

function stubFetch(renovar: () => Response | Promise<Response>, sessaoContinua = true) {
  const rotas: Record<string, () => Response | Promise<Response>> = {
    "/api/v1/auth/me": () => respostaJson(usuarioTeste({ sessao_continua: sessaoContinua })),
    "/api/v1/auth/permissions": () => respostaJson({ modulos: ["DASHBOARD"] }),
    "/health/live": () => respostaJson({ status: "ok", app: "erp-automation", env: "development" }),
    "/api/v1/empresas": () => respostaJson([]),
    "/api/v1/dashboard/resumo": () => respostaJson(resumo()),
    [RENOVAR]: renovar,
  };
  const fn = vi.fn(async (url: string) => {
    const resposta = rotas[url.split("?")[0]!];
    if (!resposta) throw new Error(`rota não esperada no teste: ${url}`);
    return resposta();
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const renovacoes = (fn: ReturnType<typeof stubFetch>) => fn.mock.calls.filter(([url]) => url === RENOVAR);
const avancar = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

async function abrirDashboard() {
  render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <AuthProvider>
        <AppRoutes />
        <LocalAtual />
      </AuthProvider>
    </MemoryRouter>,
  );
  expect(await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.sessionStorage.clear();
  salvarSessao({ token: "tok-antigo", expiraEm: Date.now() + 60_000 });
});

afterEach(() => {


  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("sessão contínua (modo TV)", () => {
  it("renova antes de expirar e continua logado depois da validade original", async () => {
    const fn = stubFetch(() => respostaJson(tokenTeste({ sessao_continua: true }, "tok-novo")));
    await abrirDashboard();

    await avancar(31_000);
    const [, init] = renovacoes(fn)[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-antigo");
    expect(lerSessao()?.token).toBe("tok-novo");

    await avancar(60_000);
    expect(screen.getByTestId("local")).toHaveTextContent("/dashboard");
    expect(renovacoes(fn)).toHaveLength(1);
  });

  it("sem a opção, não renova e a sessão termina na expiração", async () => {
    const fn = stubFetch(() => respostaJson({}), false);
    await abrirDashboard();

    await avancar(61_000);
    expect(renovacoes(fn)).toHaveLength(0);
    expect(screen.getByTestId("local")).toHaveTextContent("/login");
  });

  it("403 (opção desligada pelo ADMIN) para de renovar; a sessão termina na expiração", async () => {
    const fn = stubFetch(() => respostaJson({ detail: "Renovação de sessão não habilitada para este usuário." }, 403));
    await abrirDashboard();

    await avancar(31_000);
    expect(renovacoes(fn)).toHaveLength(1);
    expect(screen.getByTestId("local")).toHaveTextContent("/dashboard");

    await avancar(30_000);
    expect(renovacoes(fn)).toHaveLength(1);
    expect(screen.getByTestId("local")).toHaveTextContent("/login");
  });

  it("sem rede, tenta de novo até conseguir", async () => {
    let tentativas = 0;
    const fn = stubFetch(() => {
      tentativas += 1;
      if (tentativas === 1) throw new TypeError("Failed to fetch");
      return respostaJson(tokenTeste({ sessao_continua: true }, "tok-novo"));
    });
    await abrirDashboard();

    await avancar(31_000);
    expect(lerSessao()?.token).toBe("tok-antigo");
    await avancar(16_000);
    expect(renovacoes(fn)).toHaveLength(2);
    expect(lerSessao()?.token).toBe("tok-novo");
    expect(screen.getByTestId("local")).toHaveTextContent("/dashboard");
  });
});
