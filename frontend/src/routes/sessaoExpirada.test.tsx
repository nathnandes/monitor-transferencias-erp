

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../features/auth/AuthProvider";
import { MSG_SESSAO_EXPIRADA } from "../features/auth/LoginPage";
import { salvarSessao } from "../features/auth/sessaoArmazenada";
import { TITULO_DASHBOARD } from "../features/dashboard/DashboardPage";
import { resumo, respostaJson } from "../test/factories";
import { LocalAtual, usuarioTeste } from "../test/sessao";
import { AppRoutes } from "./AppRoutes";

type Rotas = Record<string, () => Response>;

const NAO_AUTENTICADO = () => respostaJson({ detail: "Não autenticado." }, 401);

function stubFetch(sobrescrever: Rotas = {}) {
  const rotas: Rotas = {
    "/api/v1/auth/me": () => respostaJson(usuarioTeste()),
    "/api/v1/auth/permissions": () => respostaJson({ modulos: ["DASHBOARD"] }),
    "/health/live": () => respostaJson({ status: "ok", app: "erp-automation", env: "development" }),
    "/api/v1/empresas": () => respostaJson([]),
    "/api/v1/dashboard/resumo": () => respostaJson(resumo()),
    ...sobrescrever,
  };
  const fn = vi.fn(async (url: string) => {
    const caminho = url.split("?")[0]!;
    const resposta = rotas[caminho];
    if (!resposta) throw new Error(`rota não esperada no teste: ${caminho}`);
    return resposta();
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderApp(rota: string) {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <AuthProvider>
        <AppRoutes />
        <LocalAtual />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.sessionStorage.clear();
  salvarSessao({ token: "tok-antigo", expiraEm: Date.now() + 60_000 });
});

afterEach(() => vi.unstubAllGlobals());

describe("sessão expirada ou recusada", () => {
  it("envia Authorization: Bearer em todas as chamadas autenticadas", async () => {
    const fn = stubFetch();
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();

    const chamadasApi = () => fn.mock.calls.filter(([url]) => String(url).startsWith("/api/"));

    await waitFor(() => expect(chamadasApi().length).toBeGreaterThanOrEqual(4));
    const autenticadas = chamadasApi();
    for (const [, init] of autenticadas as unknown as [string, RequestInit][]) {
      expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-antigo");
    }
  });

  it("401 numa API de dados encerra a sessão e leva ao /login com aviso", async () => {
    stubFetch({ "/api/v1/dashboard/resumo": NAO_AUTENTICADO });
    renderApp("/dashboard");

    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeInTheDocument();
    expect(screen.getByTestId("local")).toHaveTextContent("/login");
    expect(screen.getByText(MSG_SESSAO_EXPIRADA)).toBeInTheDocument();
    expect(window.sessionStorage.getItem("erp.sessao")).toBeNull();
  });

  it("token guardado recusado em /me: volta ao /login sem mostrar dados", async () => {
    const fn = stubFetch({ "/api/v1/auth/me": NAO_AUTENTICADO, "/api/v1/auth/permissions": NAO_AUTENTICADO });
    renderApp("/dashboard");

    expect(await screen.findByText(MSG_SESSAO_EXPIRADA)).toBeInTheDocument();
    expect(fn.mock.calls.some(([url]) => String(url).includes("/dashboard/resumo"))).toBe(false);
  });

  it("403 da API não derruba a sessão: o erro fica na tela", async () => {
    stubFetch({
      "/api/v1/dashboard/resumo": () => respostaJson({ detail: "Sem permissão para acessar este recurso." }, 403),
    });
    renderApp("/dashboard");

    expect((await screen.findAllByText("Sem permissão para acessar este recurso.")).length).toBeGreaterThan(0);
    expect(screen.getByTestId("local")).toHaveTextContent("/dashboard");
    expect(window.sessionStorage.getItem("erp.sessao")).not.toBeNull();
  });

  it("encerra a sessão quando o token expira, mesmo sem nova requisição", async () => {
    window.sessionStorage.clear();
    salvarSessao({ token: "tok-curto", expiraEm: Date.now() + 400 });
    stubFetch();
    renderApp("/dashboard");

    expect(await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(MSG_SESSAO_EXPIRADA)).toBeInTheDocument(), { timeout: 3000 });
    expect(window.sessionStorage.getItem("erp.sessao")).toBeNull();
  });
});
