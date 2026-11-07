

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../features/auth/AuthProvider";
import { MSG_CREDENCIAIS, MSG_SAIU } from "../features/auth/LoginPage";
import { TITULO_ADMIN_USUARIOS } from "../features/admin/AdminUsuariosPage";
import { TITULO_TROCA_SENHA } from "../features/auth/TrocaSenhaObrigatoriaPage";
import { ROTA_MINHA_SENHA, TITULO_MINHA_SENHA } from "../features/auth/MinhaSenhaPage";
import { salvarSessao } from "../features/auth/sessaoArmazenada";
import { TITULO_DASHBOARD } from "../features/dashboard/DashboardPage";
import { TITULO_FINANCEIRO } from "../features/financeiro/FinanceiroPage";
import { ApiError } from "../services/apiClient";
import { listarUsuarios } from "../services/adminUsuariosService";
import * as authService from "../services/authService";
import { getHealthLive, getResumoDashboard } from "../services/dashboardService";
import { getEmpresas } from "../services/empresasService";
import { getResumoFinanceiro } from "../services/financeiroService";
import { coletarTransferencias, getTransferencias } from "../services/transferenciasService";
import { pagina, resumo, resumoFinanceiro } from "../test/factories";
import { LocalAtual, tokenTeste, usuarioTeste } from "../test/sessao";
import type { Modulo, TokenAcesso, Usuario } from "../types/auth";
import { AppRoutes } from "./AppRoutes";
import { TITULO_403 } from "./paginas";

vi.mock("../services/authService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../services/authService")>()),
  login: vi.fn(),
  getMe: vi.fn(),
  getPermissoes: vi.fn(),
  trocarSenha: vi.fn(),
  logout: vi.fn(),
}));
vi.mock("../services/dashboardService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../services/dashboardService")>()),
  getResumoDashboard: vi.fn(),
  getHealthLive: vi.fn(),
}));
vi.mock("../services/empresasService", () => ({ getEmpresas: vi.fn() }));
vi.mock("../services/financeiroService", () => ({
  getResumoFinanceiro: vi.fn(),
  getParcelas: vi.fn().mockResolvedValue({
    total: 0,
    pagina: 1,
    tamanho_pagina: 50,
    total_paginas: 0,
    valor: "0",
    valor_pago: "0",
    valor_pendente: "0",
    itens: [],
  }),
}));
vi.mock("../services/adminUsuariosService", () => ({ listarUsuarios: vi.fn() }));
vi.mock("../services/transferenciasService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../services/transferenciasService")>()),
  getTransferencias: vi.fn(),
  coletarTransferencias: vi.fn(),
  getTransferencia: vi.fn(),
}));

const SENHA = "Senha-Ficticia-1";
const NOVA_SENHA = "Outra-Ficticia-2";

function usuarioNoBackend({ modulos = ["DASHBOARD", "TRANSFERENCIAS"] as Modulo[], usuario = usuarioTeste() } = {}) {
  vi.mocked(authService.login).mockResolvedValue({ ...tokenTeste(), user: usuario });
  vi.mocked(authService.getMe).mockResolvedValue(usuario);
  vi.mocked(authService.getPermissoes).mockResolvedValue({ modulos });
}


function renderLogado(rota: string) {
  salvarSessao({ token: "token-guardado", expiraEm: Date.now() + 60_000 });
  return renderApp(rota);
}

function renderApp(rota = "/") {
  return render(
    <MemoryRouter initialEntries={[rota]}>
      <AuthProvider>
        <AppRoutes />
        <LocalAtual />
      </AuthProvider>
    </MemoryRouter>,
  );
}

const local = () => screen.getByTestId("local").textContent;

async function preencherLogin(usuario = "maria", senha = SENHA) {
  await userEvent.type(await screen.findByLabelText("Usuário"), usuario);
  await userEvent.type(screen.getByLabelText("Senha"), senha);
  await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
}

function adiado<T>() {
  let resolver!: (v: T) => void;
  const promessa = new Promise<T>((res) => (resolver = res));
  return { promessa, resolver };
}

const menu = () => screen.getAllByRole("navigation", { name: "Módulos" })[0]!;

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  vi.mocked(authService.logout).mockResolvedValue();
  vi.mocked(getHealthLive).mockResolvedValue({ status: "ok", app: "erp-automation", env: "development" });
  vi.mocked(getResumoDashboard).mockResolvedValue(resumo());
  vi.mocked(getEmpresas).mockResolvedValue([]);
  vi.mocked(getResumoFinanceiro).mockResolvedValue(resumoFinanceiro());
  vi.mocked(getTransferencias).mockResolvedValue(pagina([]));
  vi.mocked(coletarTransferencias).mockResolvedValue({ itens: [], total: 0, truncado: false });
  vi.mocked(listarUsuarios).mockResolvedValue({ total: 0, pagina: 1, tamanho_pagina: 20, total_paginas: 0, itens: [] });
  usuarioNoBackend();
});

describe("rota protegida sem sessão", () => {
  it("vai para /login e não chama nenhuma API de dados", async () => {
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeInTheDocument();
    expect(local()).toBe("/login");
    expect(screen.getByText("ERP Automation")).toBeInTheDocument();
    expect(getResumoDashboard).not.toHaveBeenCalled();

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.queryByText(/esqueci|cadastr[ae]-se|e-mail/i)).not.toBeInTheDocument();
  });
});

describe("login", () => {
  it("válido: busca /me e /permissions, guarda só o token e abre a tela inicial (não a rota pedida)", async () => {
    renderApp("/transferencias?periodo=personalizado&data_inicial=2026-01-01");
    await preencherLogin();


    await waitFor(() => expect(local()).toBe("/dashboard"));
    expect(screen.getByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hoje" })).toHaveAttribute("aria-pressed", "true");
    expect(authService.login).toHaveBeenCalledWith("maria", SENHA);
    expect(authService.getMe).toHaveBeenCalledWith("token-de-teste");
    expect(authService.getPermissoes).toHaveBeenCalledWith("token-de-teste");

    const guardado = window.sessionStorage.getItem("erp.sessao")!;
    expect(guardado).toContain("token-de-teste");
    expect(guardado).not.toContain(SENHA);
    expect(window.localStorage.getItem("erp.sessao")).toBeNull();
    expect(window.location.href).not.toContain(SENHA);
  });

  it("com perfil de acesso: abre a tela inicial do perfil e esconde as sub-abas fora dele", async () => {
    vi.mocked(authService.getPermissoes).mockResolvedValue({
      modulos: ["DASHBOARD", "TRANSFERENCIAS"],
      abas: [],
      tela_inicial: "TRANSFERENCIAS",
    });
    renderApp("/dashboard");
    await preencherLogin();

    await waitFor(() => expect(local()).toBe("/transferencias"));
    expect(await screen.findByRole("heading", { level: 1, name: "Transferências" })).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: "Controle" })).not.toBeInTheDocument();
  });

  it("inválido: mensagem genérica, senha apagada e continua no /login", async () => {
    vi.mocked(authService.login).mockRejectedValue(new ApiError(MSG_CREDENCIAIS, "http", 401));
    renderApp("/");
    await preencherLogin("maria", "errada");

    expect(await screen.findByRole("alert")).toHaveTextContent(MSG_CREDENCIAIS);
    expect(screen.getByLabelText("Senha")).toHaveValue("");
    expect(screen.getByLabelText("Usuário")).toHaveValue("maria");
    expect(local()).toBe("/login");
    expect(window.sessionStorage.getItem("erp.sessao")).toBeNull();
  });

  it("mostra carregando e bloqueia o formulário enquanto espera", async () => {
    const pendente = adiado<TokenAcesso>();
    vi.mocked(authService.login).mockReturnValue(pendente.promessa);
    renderApp("/");
    await preencherLogin();

    const botao = screen.getByRole("button", { name: "Entrando…" });
    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Senha")).toBeDisabled();

    pendente.resolver(tokenTeste());
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();
  });

  it("muitas tentativas (429) e falha de rede mostram a mensagem do erro", async () => {
    vi.mocked(authService.login)
      .mockRejectedValueOnce(new ApiError("Muitas tentativas. Tente novamente mais tarde.", "http", 429))
      .mockRejectedValueOnce(new ApiError("Não foi possível conectar à API.", "rede"));
    renderApp("/");
    await preencherLogin();
    expect(await screen.findByRole("alert")).toHaveTextContent("Muitas tentativas");

    await userEvent.type(screen.getByLabelText("Senha"), SENHA);
    await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível conectar à API."));
  });

  it("campos vazios não chamam a API", async () => {
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Entrar" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Informe usuário e senha.");
    expect(authService.login).not.toHaveBeenCalled();
  });

  it("sessão guardada é conferida em /me ao recarregar, sem novo login", async () => {
    salvarSessao({ token: "token-guardado", expiraEm: Date.now() + 60_000 });
    renderApp("/dashboard");
    expect(screen.getByRole("status")).toHaveTextContent("Verificando sessão…");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();
    expect(authService.getMe).toHaveBeenCalledWith("token-guardado", expect.any(AbortSignal));
    expect(authService.login).not.toHaveBeenCalled();
  });
});

describe("permissões", () => {
  it("o menu mostra só os módulos liberados e / leva ao primeiro deles", async () => {
    usuarioNoBackend({ modulos: ["TRANSFERENCIAS", "ESTOQUE"] });
    renderApp("/");
    await preencherLogin();

    await waitFor(() => expect(local()).toBe("/transferencias"));
    const links = within(menu()).getAllByRole("link").map((l) => l.textContent);
    expect(links).toEqual(["Transferências", "Estoque"]);
    expect(within(menu()).queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(within(menu()).queryByRole("link", { name: "Administração" })).not.toBeInTheDocument();
  });

  it("rota sem o módulo mostra 403 claro, sem chamar a API do módulo", async () => {
    usuarioNoBackend({ modulos: ["TRANSFERENCIAS"] });
    renderLogado("/dashboard");

    expect(await screen.findByRole("heading", { level: 1, name: TITULO_403 })).toBeInTheDocument();
    expect(screen.getByText("Você não tem permissão para acessar esta página.")).toBeInTheDocument();
    expect(screen.getByText(/peça acesso ao administrador/)).toBeInTheDocument();
    expect(local()).toBe("/dashboard");
    expect(getResumoDashboard).not.toHaveBeenCalled();
  });

  it("financeiro liberado abre a tela do módulo", async () => {
    usuarioNoBackend({ modulos: ["DASHBOARD", "FINANCEIRO"] });
    renderLogado("/financeiro");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_FINANCEIRO })).toBeInTheDocument();
    expect(screen.queryByText("Em desenvolvimento")).not.toBeInTheDocument();
    await waitFor(() => expect(getResumoFinanceiro).toHaveBeenCalled());
  });

  it("administração: ADMIN com o módulo vê o menu e a tela de usuários (/administracao redireciona)", async () => {
    usuarioNoBackend({ modulos: ["DASHBOARD", "ADMINISTRACAO"], usuario: usuarioTeste({ role: "ADMIN" }) });
    renderLogado("/administracao");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_ADMIN_USUARIOS })).toBeInTheDocument();
    expect(local()).toBe("/admin/usuarios");
    expect(within(menu()).getByRole("link", { name: "Administração" })).toHaveAttribute("href", "/admin/usuarios");
    await waitFor(() => expect(listarUsuarios).toHaveBeenCalled());
  });

  it("administração: OPERADOR não vê o menu e recebe 403, mesmo digitando a URL", async () => {

    usuarioNoBackend({ modulos: ["DASHBOARD", "ADMINISTRACAO"], usuario: usuarioTeste({ role: "OPERADOR" }) });
    renderLogado("/admin/usuarios");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_403 })).toBeInTheDocument();
    expect(within(menu()).queryByRole("link", { name: "Administração" })).not.toBeInTheDocument();
    expect(listarUsuarios).not.toHaveBeenCalled();
  });

  it("sub-aba fora do perfil de acesso: 403 mesmo digitando a URL", async () => {
    vi.mocked(authService.getPermissoes).mockResolvedValue({ modulos: ["DASHBOARD"], abas: [], tela_inicial: null });
    renderLogado("/tv");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_403 })).toBeInTheDocument();
  });

  it("módulo não liberado e sem tela: 403, não 'Em desenvolvimento'", async () => {
    renderLogado("/administracao");
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_403 })).toBeInTheDocument();
    expect(screen.queryByText("Em desenvolvimento")).not.toBeInTheDocument();
  });

  it("usuário sem nenhum módulo vê aviso próprio", async () => {
    usuarioNoBackend({ modulos: [] });
    renderApp("/");
    await preencherLogin();
    expect(await screen.findByRole("heading", { level: 1, name: "Nenhum módulo liberado" })).toBeInTheDocument();
  });
});

describe("logout", () => {
  it("remove a sessão local, avisa o backend e volta ao /login", async () => {
    renderApp("/");
    await preencherLogin();
    await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD });

    await userEvent.click(screen.getAllByRole("button", { name: "Sair" })[0]!);
    expect(await screen.findByRole("heading", { name: "Entrar" })).toBeInTheDocument();
    expect(local()).toBe("/login");
    expect(screen.getByRole("status")).toHaveTextContent(MSG_SAIU);
    expect(window.sessionStorage.getItem("erp.sessao")).toBeNull();
    expect(authService.logout).toHaveBeenCalledWith("token-de-teste");
  });
});

describe("troca obrigatória de senha", () => {
  const precisaTrocar: Usuario = usuarioTeste({ must_change_password: true });

  async function entrarPrecisandoTrocar(rota = "/dashboard") {
    usuarioNoBackend({ usuario: precisaTrocar });
    renderApp(rota);
    await preencherLogin();
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_TROCA_SENHA })).toBeInTheDocument();
  }

  async function preencherTroca(atual: string, nova: string, confirmacao = nova) {
    await userEvent.type(screen.getByLabelText("Senha atual"), atual);
    await userEvent.type(screen.getByLabelText("Nova senha"), nova);
    await userEvent.type(screen.getByLabelText("Confirme a nova senha"), confirmacao);
  }

  it("bloqueia a navegação: sem menu nem dados, em qualquer rota", async () => {
    await entrarPrecisandoTrocar("/transferencias");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(getResumoDashboard).not.toHaveBeenCalled();
    expect(getTransferencias).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Sair" })).toBeInTheDocument();
  });

  it("mostra as regras e só habilita salvar com a senha válida e confirmada", async () => {
    await entrarPrecisandoTrocar();
    const regras = screen.getByRole("list", { name: "Regras da nova senha" });
    expect(within(regras).getAllByRole("listitem")).toHaveLength(2);
    const salvar = screen.getByRole("button", { name: "Salvar nova senha" });

    await preencherTroca(SENHA, "abc");
    expect(salvar).toBeDisabled();
    expect(within(regras).getByText(/De 4 a 128 caracteres/).closest("li")).toHaveAttribute("data-atende", "false");

    await userEvent.clear(screen.getByLabelText("Nova senha"));
    await userEvent.clear(screen.getByLabelText("Confirme a nova senha"));
    await userEvent.type(screen.getByLabelText("Nova senha"), NOVA_SENHA);
    await userEvent.type(screen.getByLabelText("Confirme a nova senha"), "diferente");
    expect(screen.getByText("A confirmação não confere com a nova senha.")).toBeInTheDocument();
    expect(salvar).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Confirme a nova senha"));
    await userEvent.type(screen.getByLabelText("Confirme a nova senha"), NOVA_SENHA);
    expect(salvar).toBeEnabled();
    for (const item of within(regras).getAllByRole("listitem")) expect(item).toHaveAttribute("data-atende", "true");
  });

  it("sucesso: usa o token novo e só então libera o dashboard", async () => {
    vi.mocked(authService.trocarSenha).mockResolvedValue(tokenTeste({}, "token-novo"));
    await entrarPrecisandoTrocar();
    await preencherTroca(SENHA, NOVA_SENHA);
    await userEvent.click(screen.getByRole("button", { name: "Salvar nova senha" }));

    expect(await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD })).toBeInTheDocument();
    expect(authService.trocarSenha).toHaveBeenCalledWith(SENHA, NOVA_SENHA);
    const guardado = window.sessionStorage.getItem("erp.sessao")!;
    expect(guardado).toContain("token-novo");
    expect(guardado).not.toContain(NOVA_SENHA);
    expect(getResumoDashboard).toHaveBeenCalled();
  });

  it("senha atual errada (400): avisa, limpa os campos e continua bloqueado", async () => {
    vi.mocked(authService.trocarSenha).mockRejectedValue(new ApiError("Senha atual incorreta.", "http", 400));
    await entrarPrecisandoTrocar();
    await preencherTroca("Atual-Errada-9", NOVA_SENHA);
    await userEvent.click(screen.getByRole("button", { name: "Salvar nova senha" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Senha atual incorreta.");
    expect(screen.getByLabelText("Senha atual")).toHaveValue("");
    expect(screen.getByLabelText("Nova senha")).toHaveValue("");
    expect(screen.getByLabelText("Confirme a nova senha")).toHaveValue("");
    expect(screen.getByRole("heading", { level: 1, name: TITULO_TROCA_SENHA })).toBeInTheDocument();
  });

  it("política recusada no backend (422): lista os problemas", async () => {
    vi.mocked(authService.trocarSenha).mockRejectedValue(
      new ApiError("Nova senha não atende à política.", "http", 422, {
        detail: { mensagem: "Nova senha não atende à política.", problemas: ["a nova senha deve ser diferente da atual"] },
      }),
    );
    await entrarPrecisandoTrocar();
    await preencherTroca(SENHA, NOVA_SENHA);
    await userEvent.click(screen.getByRole("button", { name: "Salvar nova senha" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Nova senha não atende à política.");
    expect(within(alerta).getByRole("listitem")).toHaveTextContent("a nova senha deve ser diferente da atual");
  });
});

describe("minha senha (troca voluntária)", () => {
  it("abre pela barra superior, troca a senha e continua no sistema", async () => {
    vi.mocked(authService.trocarSenha).mockResolvedValue(tokenTeste({}, "token-novo"));
    usuarioNoBackend();
    renderApp("/");
    await preencherLogin();
    await screen.findByRole("heading", { level: 1, name: TITULO_DASHBOARD });

    await userEvent.click(screen.getByRole("link", { name: "Minha senha" }));
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_MINHA_SENHA })).toBeInTheDocument();
    expect(local()).toBe(ROTA_MINHA_SENHA);

    await userEvent.type(screen.getByLabelText("Senha atual"), SENHA);
    await userEvent.type(screen.getByLabelText("Nova senha"), "1234");
    await userEvent.type(screen.getByLabelText("Confirme a nova senha"), "1234");
    await userEvent.click(screen.getByRole("button", { name: "Salvar nova senha" }));

    expect(await screen.findByText(/Senha trocada\./)).toBeInTheDocument();
    expect(authService.trocarSenha).toHaveBeenCalledWith(SENHA, "1234");
    expect(window.sessionStorage.getItem("erp.sessao")).toContain("token-novo");
    expect(screen.getByLabelText("Nova senha")).toHaveValue("");
    expect(screen.getAllByRole("navigation", { name: "Módulos" }).length).toBeGreaterThan(0);
  });

  it("não exige módulo: usuário sem nenhum módulo também troca a senha", async () => {
    usuarioNoBackend({ modulos: [] });
    renderLogado(ROTA_MINHA_SENHA);
    expect(await screen.findByRole("heading", { level: 1, name: TITULO_MINHA_SENHA })).toBeInTheDocument();
  });
});
