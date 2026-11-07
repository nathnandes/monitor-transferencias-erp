

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/apiClient";
import {
  ativarUsuario,
  atualizarUsuario,
  criarPerfil,
  criarUsuario,
  desativarUsuario,
  excluirPerfil,
  listarPerfis,
  listarUsuarios,
  obterUsuario,
  redefinirSenha,
} from "../../services/adminUsuariosService";
import { authFalso, renderComSessao, usuarioTeste } from "../../test/sessao";
import type { PaginaUsuarios, PerfilAdmin, UsuarioAdmin, UsuarioAdminDetalhe } from "../../types/admin";
import { AdminUsuariosPage, NOTA_PROPRIA_CONTA } from "./AdminUsuariosPage";
import { AVISO_PRIMEIRO_LOGIN } from "./components/CriarUsuarioModal";
import { AVISO_PROPRIO_USUARIO } from "./components/EditarUsuarioModal";

vi.mock("../../services/adminUsuariosService", () => ({
  listarUsuarios: vi.fn(),
  obterUsuario: vi.fn(),
  criarUsuario: vi.fn(),
  atualizarUsuario: vi.fn(),
  redefinirSenha: vi.fn(),
  ativarUsuario: vi.fn(),
  desativarUsuario: vi.fn(),
  listarPerfis: vi.fn(),
  criarPerfil: vi.fn(),
  atualizarPerfil: vi.fn(),
  excluirPerfil: vi.fn(),
}));

const SENHA_TEMP = "Temporaria-123";

function usuarioAdmin(parcial: Partial<UsuarioAdmin> = {}): UsuarioAdmin {
  return {
    id: 7,
    username: "joao.silva",
    nome_exibicao: "João Silva",
    role: "OPERADOR",
    ativo: true,
    must_change_password: true,
    sessao_continua: false,
    perfil: null,
    last_login_at: null,
    created_at: "2026-09-29T13:00:00Z",
    updated_at: "2026-09-29T13:00:00Z",
    ...parcial,
  };
}

function detalheAdmin(parcial: Partial<UsuarioAdminDetalhe> = {}): UsuarioAdminDetalhe {
  return { ...usuarioAdmin(parcial), modulos: ["DASHBOARD"], ...parcial };
}

function paginaUsuarios(itens: UsuarioAdmin[], extra: Partial<PaginaUsuarios> = {}): PaginaUsuarios {
  return { total: itens.length, pagina: 1, tamanho_pagina: 20, total_paginas: itens.length ? 1 : 0, itens, ...extra };
}

const EU = usuarioTeste({ id: 1, username: "maria.admin", nome_exibicao: "Maria Admin", role: "ADMIN" });
const eu = usuarioAdmin({ id: 1, username: "maria.admin", nome_exibicao: "Maria Admin", role: "ADMIN", must_change_password: false, last_login_at: "2026-09-29T14:30:00Z" });
const joao = usuarioAdmin();
const inativo = usuarioAdmin({ id: 9, username: "ana.inativa", nome_exibicao: "Ana", ativo: false, must_change_password: false });

function renderPagina() {
  return renderComSessao(<AdminUsuariosPage />, {
    rota: "/admin/usuarios",
    auth: authFalso(["DASHBOARD", "ADMINISTRACAO"], EU),
  });
}

const linha = (username: string) => screen.getByText(username).closest("tr")!;

async function abrirCriacao() {
  await userEvent.click(screen.getByRole("button", { name: "Criar usuário" }));
  return screen.findByRole("dialog", { name: "Criar usuário" });
}

async function preencherCriacao(dialogo: HTMLElement, { username = "Joao.Novo", nome = "João Novo", senha = SENHA_TEMP, confirmacao = SENHA_TEMP } = {}) {
  const d = within(dialogo);
  if (username) await userEvent.type(d.getByLabelText("Username"), username);
  if (nome) await userEvent.type(d.getByLabelText("Nome exibido"), nome);
  if (senha) await userEvent.type(d.getByLabelText("Senha"), senha);
  if (confirmacao) await userEvent.type(d.getByLabelText("Confirme a senha"), confirmacao);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listarPerfis).mockResolvedValue([]);
  vi.mocked(listarUsuarios).mockResolvedValue(paginaUsuarios([eu, joao, inativo]));
});

describe("listagem", () => {
  it("mostra carregando e depois a tabela, só com campos seguros", async () => {

    const vazado = { ...joao, password_hash: "$argon2id$v=19$segredo", token: "eyJ.segredo" } as UsuarioAdmin;
    vi.mocked(listarUsuarios).mockResolvedValue(paginaUsuarios([eu, vazado]));
    renderPagina();

    expect(screen.getByRole("status")).toHaveTextContent("Carregando usuários…");
    const tabela = await screen.findByRole("table", { name: "Usuários locais" });
    const cabecalhos = within(tabela).getAllByRole("columnheader").map((c) => c.textContent);
    expect(cabecalhos).toEqual(["Username", "Nome", "Papel", "Perfil de acesso", "Status", "Criado em", "Último login", "Ações"]);

    const l = linha("joao.silva");
    expect(within(l).getByText("João Silva")).toBeInTheDocument();
    expect(within(l).getByText("OPERADOR")).toBeInTheDocument();
    expect(within(l).getByText("Ativo")).toBeInTheDocument();
    expect(within(l).getByText("Troca de senha pendente")).toBeInTheDocument();
    expect(within(l).getByText("29/09/2026, 09:00")).toBeInTheDocument();
    expect(within(l).getByText("Nunca")).toBeInTheDocument();
    expect(within(linha("maria.admin")).getByText("(você)")).toBeInTheDocument();

    expect(document.body.textContent).not.toMatch(/argon2|segredo|eyJ/);
    expect(listarUsuarios).toHaveBeenCalledWith({ busca: "", role: "", ativo: "" }, 1, 20, expect.any(AbortSignal));
  });

  it("erro da API aparece com Tentar novamente", async () => {
    vi.mocked(listarUsuarios)
      .mockRejectedValueOnce(new ApiError("A API respondeu com erro HTTP 500.", "http", 500))
      .mockResolvedValueOnce(paginaUsuarios([joao]));
    renderPagina();

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("Falha ao carregar os usuários");
    expect(alerta).toHaveTextContent("HTTP 500");
    await userEvent.click(within(alerta).getByRole("button", { name: "Tentar novamente" }));
    expect(await screen.findByText("joao.silva")).toBeInTheDocument();
  });

  it("403 da API (URL manipulada, permissão revogada) mostra mensagem clara", async () => {
    vi.mocked(listarUsuarios).mockRejectedValue(new ApiError("Sem permissão para acessar este recurso.", "http", 403));
    renderPagina();
    expect(await screen.findByRole("alert")).toHaveTextContent("exige papel ADMIN com o módulo Administração");
  });

  it("vazio: sem filtros e com filtros", async () => {
    vi.mocked(listarUsuarios).mockResolvedValue(paginaUsuarios([]));
    renderPagina();
    expect(await screen.findByText("Nenhum usuário cadastrado.")).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Buscar por username ou nome"), "zzz");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    expect(await screen.findByText("Nenhum usuário atende aos filtros.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    await waitFor(() =>
      expect(listarUsuarios).toHaveBeenLastCalledWith({ busca: "", role: "", ativo: "" }, 1, 20, expect.any(AbortSignal)),
    );
  });

  it("busca e filtros só se aplicam em Buscar", async () => {
    renderPagina();
    await screen.findByText("joao.silva");
    const chamadas = vi.mocked(listarUsuarios).mock.calls.length;

    await userEvent.type(screen.getByLabelText("Buscar por username ou nome"), " joao ");
    await userEvent.selectOptions(screen.getByLabelText("Papel"), "OPERADOR");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "false");
    expect(listarUsuarios).toHaveBeenCalledTimes(chamadas);

    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));
    await waitFor(() =>
      expect(listarUsuarios).toHaveBeenLastCalledWith(
        { busca: "joao", role: "OPERADOR", ativo: "false" },
        1,
        20,
        expect.any(AbortSignal),
      ),
    );
  });

  it("paginação preserva os filtros", async () => {
    vi.mocked(listarUsuarios).mockImplementation(async (_f, p = 1) =>
      paginaUsuarios([usuarioAdmin({ id: 100 + p, username: `usuario.p${p}` })], { total: 45, total_paginas: 3, pagina: p }),
    );
    renderPagina();
    await screen.findByText("usuario.p1");
    await userEvent.selectOptions(screen.getByLabelText("Papel"), "ADMIN");
    await userEvent.click(screen.getByRole("button", { name: "Buscar" }));

    await userEvent.click(await screen.findByRole("button", { name: "Próxima" }));
    expect(await screen.findByText("usuario.p2")).toBeInTheDocument();
    expect(listarUsuarios).toHaveBeenLastCalledWith({ busca: "", role: "ADMIN", ativo: "" }, 2, 20, expect.any(AbortSignal));
  });
});

describe("criar usuário", () => {
  it("OPERADOR: sem Administração, envia os módulos marcados e avisa da troca no primeiro login", async () => {
    vi.mocked(criarUsuario).mockResolvedValue(detalheAdmin({ id: 20, username: "joao.novo", modulos: ["DASHBOARD", "TRANSFERENCIAS"] }));
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    const d = within(dialogo);

    expect(d.getByRole("radio", { name: "OPERADOR" })).toBeChecked();
    const administracao = d.getByRole("checkbox", { name: /Administração/ });
    expect(administracao).not.toBeChecked();
    expect(administracao).toBeDisabled();
    expect(d.getByText("Não permitido para OPERADOR.")).toBeInTheDocument();
    expect(within(d.getByRole("list", { name: "Regras da senha" })).getAllByRole("listitem")).toHaveLength(1);

    await preencherCriacao(dialogo);
    await userEvent.click(d.getByRole("checkbox", { name: "Dashboard" }));
    await userEvent.click(d.getByRole("checkbox", { name: "Transferências" }));
    const chamadasLista = vi.mocked(listarUsuarios).mock.calls.length;
    await userEvent.click(d.getByRole("button", { name: "Criar usuário" }));

    expect(criarUsuario).toHaveBeenCalledWith({
      username: "joao.novo",
      nome_exibicao: "João Novo",
      password_temporaria: SENHA_TEMP,
      role: "OPERADOR",
      modulos: ["DASHBOARD", "TRANSFERENCIAS"],
      sessao_continua: false,
      exigir_troca_senha: false,
      perfil_id: null,
    });
    const sucesso = await d.findByText(/Usuário/, { selector: "p" });
    expect(sucesso).toHaveTextContent("joao.novo");
    expect(d.getByText(AVISO_PRIMEIRO_LOGIN)).toBeInTheDocument();

    expect(d.queryByLabelText("Senha")).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(SENHA_TEMP);
    await waitFor(() => expect(vi.mocked(listarUsuarios).mock.calls.length).toBeGreaterThan(chamadasLista));

    await userEvent.click(d.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(AVISO_PRIMEIRO_LOGIN);
  });

  it("ADMIN: Administração vem marcada e travada, e Dashboard entra por padrão", async () => {
    vi.mocked(criarUsuario).mockResolvedValue(detalheAdmin({ id: 21, username: "outro.admin", role: "ADMIN" }));
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    const d = within(dialogo);

    await userEvent.click(d.getByRole("radio", { name: "ADMIN" }));
    const administracao = d.getByRole("checkbox", { name: /Administração/ });
    expect(administracao).toBeChecked();
    expect(administracao).toBeDisabled();
    expect(d.getByRole("checkbox", { name: "Dashboard" })).toBeChecked();

    await preencherCriacao(dialogo, { username: "outro.admin", nome: "Outro Admin" });
    await userEvent.click(d.getByRole("button", { name: "Criar usuário" }));
    expect(criarUsuario).toHaveBeenCalledWith(
      expect.objectContaining({ role: "ADMIN", modulos: ["DASHBOARD", "ADMINISTRACAO"] }),
    );
  });

  it("trocar ADMIN → OPERADOR remove Administração antes de enviar", async () => {
    vi.mocked(criarUsuario).mockResolvedValue(detalheAdmin());
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    const d = within(dialogo);
    await userEvent.click(d.getByRole("radio", { name: "ADMIN" }));
    await userEvent.click(d.getByRole("radio", { name: "OPERADOR" }));
    expect(d.getByRole("checkbox", { name: /Administração/ })).not.toBeChecked();

    await preencherCriacao(dialogo);
    await userEvent.click(d.getByRole("button", { name: "Criar usuário" }));
    expect(vi.mocked(criarUsuario).mock.calls[0]![0].modulos).not.toContain("ADMINISTRACAO");
  });

  it("valida os campos antes de enviar, com erros ligados aos campos", async () => {
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    const d = within(dialogo);

    await preencherCriacao(dialogo, { username: "a b", nome: "", senha: "abc", confirmacao: "outra" });
    await userEvent.click(d.getByRole("button", { name: "Criar usuário" }));

    expect(criarUsuario).not.toHaveBeenCalled();
    const username = d.getByLabelText("Username");
    expect(username).toHaveAttribute("aria-invalid", "true");
    expect(username).toHaveAccessibleDescription(expect.stringContaining("Use de 3 a 50 caracteres"));
    expect(d.getByLabelText("Nome exibido")).toHaveAccessibleDescription("Informe o nome exibido.");
    expect(d.getByLabelText("Senha")).toHaveAttribute("aria-invalid", "true");
    expect(d.getByLabelText("Confirme a senha")).toHaveAccessibleDescription(
      "A confirmação não confere com a senha.",
    );
  });

  it("erro da API (409 username em uso) aparece e os campos de senha são limpos", async () => {
    vi.mocked(criarUsuario).mockRejectedValue(new ApiError("Username já cadastrado.", "http", 409));
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    const d = within(dialogo);
    await preencherCriacao(dialogo);
    await userEvent.click(d.getByRole("button", { name: "Criar usuário" }));

    expect(await d.findByRole("alert")).toHaveTextContent("Username já cadastrado.");
    expect(d.getByLabelText("Senha")).toHaveValue("");
    expect(d.getByLabelText("Confirme a senha")).toHaveValue("");
    expect(d.getByLabelText("Username")).toHaveValue("Joao.Novo");
  });

  it("422 da política lista os problemas vindos do backend", async () => {
    vi.mocked(criarUsuario).mockRejectedValue(
      new ApiError("Senha temporária não atende à política.", "http", 422, {
        detail: { mensagem: "Senha temporária não atende à política.", problemas: ["ao menos um numero"] },
      }),
    );
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    await preencherCriacao(dialogo);
    await userEvent.click(within(dialogo).getByRole("button", { name: "Criar usuário" }));

    const alerta = await within(dialogo).findByRole("alert");
    expect(alerta).toHaveTextContent("Senha temporária não atende à política.");
    expect(within(alerta).getByRole("listitem")).toHaveTextContent("ao menos um numero");
  });

  it("fechar o modal (Esc) descarta as senhas digitadas", async () => {
    renderPagina();
    await screen.findByText("joao.silva");
    let dialogo = await abrirCriacao();
    await preencherCriacao(dialogo);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    dialogo = await abrirCriacao();
    expect(within(dialogo).getByLabelText("Senha")).toHaveValue("");
    expect(within(dialogo).getByLabelText("Confirme a senha")).toHaveValue("");
    expect(within(dialogo).getByLabelText("Username")).toHaveValue("");
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});

describe("editar usuário", () => {
  it("carrega o detalhe do backend e envia só o que mudou", async () => {
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin({ modulos: ["DASHBOARD"] }));
    vi.mocked(atualizarUsuario).mockResolvedValue(detalheAdmin({ nome_exibicao: "João S." }));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Editar joao.silva" }));
    const dialogo = await screen.findByRole("dialog", { name: "Editar usuário" });
    const d = within(dialogo);

    const nome = await d.findByLabelText("Nome exibido");
    expect(obterUsuario).toHaveBeenCalledWith(7, expect.any(AbortSignal));
    expect(d.getByLabelText("Username")).toHaveValue("joao.silva");
    expect(d.getByLabelText("Username")).toHaveAttribute("readonly");
    expect(d.getByRole("checkbox", { name: "Dashboard" })).toBeChecked();
    expect(d.queryByLabelText(/senha/i)).not.toBeInTheDocument();

    await userEvent.clear(nome);
    await userEvent.type(nome, "João S.");
    await userEvent.click(d.getByRole("checkbox", { name: "Transferências" }));
    await userEvent.click(d.getByRole("button", { name: "Salvar alterações" }));

    expect(atualizarUsuario).toHaveBeenCalledWith(7, {
      nome_exibicao: "João S.",
      modulos: ["DASHBOARD", "TRANSFERENCIAS"],
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("Alterações de joao.silva salvas.");
  });

  it("promover a ADMIN inclui Administração; desativar vai no mesmo PATCH", async () => {
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin({ modulos: [] }));
    vi.mocked(atualizarUsuario).mockResolvedValue(detalheAdmin());
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Editar joao.silva" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar usuário" }));

    await userEvent.click(await d.findByRole("radio", { name: "ADMIN" }));
    await userEvent.click(d.getByRole("checkbox", { name: /Usuário ativo/ }));
    await userEvent.click(d.getByRole("button", { name: "Salvar alterações" }));
    expect(atualizarUsuario).toHaveBeenCalledWith(7, { role: "ADMIN", ativo: false, modulos: ["ADMINISTRACAO"] });
  });

  it("sem mudanças, não chama a API", async () => {
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin());
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Editar joao.silva" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar usuário" }));
    await userEvent.click(await d.findByRole("button", { name: "Salvar alterações" }));
    expect(d.getByText("Nada foi alterado.")).toBeInTheDocument();
    expect(atualizarUsuario).not.toHaveBeenCalled();
  });

  it("na própria conta, perfil e ativo ficam travados", async () => {
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin({ ...eu, modulos: ["DASHBOARD", "ADMINISTRACAO"] }));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Editar maria.admin" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar usuário" }));

    expect(await d.findByRole("radio", { name: "OPERADOR" })).toBeDisabled();
    expect(d.getByRole("checkbox", { name: /Usuário ativo/ })).toBeDisabled();
    expect(d.getByText(AVISO_PROPRIO_USUARIO)).toBeInTheDocument();
  });

  it("recusa do backend (409 último ADMIN) aparece como veio", async () => {
    const msg = "Operação recusada: o sistema ficaria sem nenhum ADMIN ativo.";
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin({ role: "ADMIN", modulos: ["ADMINISTRACAO"] }));
    vi.mocked(atualizarUsuario).mockRejectedValue(new ApiError(msg, "http", 409));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Editar joao.silva" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar usuário" }));
    await userEvent.click(await d.findByRole("radio", { name: "OPERADOR" }));
    await userEvent.click(d.getByRole("button", { name: "Salvar alterações" }));
    expect(await d.findByRole("alert")).toHaveTextContent(msg);
    expect(screen.getByRole("dialog", { name: "Editar usuário" })).toBeInTheDocument();
  });
});

describe("ações", () => {
  it("desativar pede confirmação; cancelar não chama a API", async () => {
    vi.mocked(desativarUsuario).mockResolvedValue(detalheAdmin({ ativo: false }));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Desativar joao.silva" }));

    let confirmacao = await screen.findByRole("alertdialog", { name: "Desativar usuário?" });
    expect(confirmacao).toHaveAccessibleDescription(expect.stringContaining("joao.silva não conseguirá mais entrar"));
    await userEvent.click(within(confirmacao).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(desativarUsuario).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Desativar joao.silva" }));
    confirmacao = await screen.findByRole("alertdialog", { name: "Desativar usuário?" });
    await userEvent.click(within(confirmacao).getByRole("button", { name: "Desativar" }));
    expect(desativarUsuario).toHaveBeenCalledWith(7);
    expect(await screen.findByRole("status")).toHaveTextContent("Usuário joao.silva desativado.");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("desativar recusado pelo backend (último ADMIN) mostra a mensagem recebida", async () => {
    const msg = "Operação recusada: o sistema ficaria sem nenhum ADMIN ativo.";
    vi.mocked(desativarUsuario).mockRejectedValue(new ApiError(msg, "http", 409));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Desativar joao.silva" }));
    const confirmacao = await screen.findByRole("alertdialog");
    await userEvent.click(within(confirmacao).getByRole("button", { name: "Desativar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(msg);
  });

  it("ativar chama a API e dá retorno", async () => {
    vi.mocked(ativarUsuario).mockResolvedValue(detalheAdmin({ ...inativo, ativo: true }));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Ativar ana.inativa" }));
    expect(ativarUsuario).toHaveBeenCalledWith(9);
    expect(await screen.findByRole("status")).toHaveTextContent("Usuário ana.inativa ativado.");
  });

  it("resetar senha: confirmação, depois senha temporária; campos limpos e senha nunca exibida", async () => {
    vi.mocked(redefinirSenha).mockResolvedValue(detalheAdmin());
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Resetar senha de joao.silva" }));

    const confirmacao = await screen.findByRole("alertdialog", { name: "Redefinir senha?" });
    expect(screen.queryByLabelText("Senha")).not.toBeInTheDocument();
    await userEvent.click(within(confirmacao).getByRole("button", { name: "Continuar" }));

    const dialogo = await screen.findByRole("dialog", { name: "Redefinir senha" });
    const d = within(dialogo);
    await userEvent.type(d.getByLabelText("Senha"), SENHA_TEMP);
    await userEvent.type(d.getByLabelText("Confirme a senha"), SENHA_TEMP);
    await userEvent.click(d.getByRole("button", { name: "Redefinir senha" }));

    expect(redefinirSenha).toHaveBeenCalledWith(7, SENHA_TEMP, false);
    expect(await screen.findByRole("status")).toHaveTextContent("Senha de joao.silva redefinida.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(SENHA_TEMP);
    expect(window.location.href).not.toContain(SENHA_TEMP);
  });

  it("resetar senha: cancelar a confirmação não abre o formulário", async () => {
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Resetar senha de joao.silva" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(redefinirSenha).not.toHaveBeenCalled();
  });

  it("reset com falha: mostra o erro e limpa os campos", async () => {
    vi.mocked(redefinirSenha).mockRejectedValue(new ApiError("Usuário não encontrado.", "http", 404));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Resetar senha de joao.silva" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Continuar" }));
    const d = within(await screen.findByRole("dialog", { name: "Redefinir senha" }));
    await userEvent.type(d.getByLabelText("Senha"), SENHA_TEMP);
    await userEvent.type(d.getByLabelText("Confirme a senha"), SENHA_TEMP);
    await userEvent.click(d.getByRole("button", { name: "Redefinir senha" }));

    expect(await d.findByRole("alert")).toHaveTextContent("Usuário não encontrado.");
    expect(d.getByLabelText("Senha")).toHaveValue("");
    expect(d.getByLabelText("Confirme a senha")).toHaveValue("");
  });

  it("na própria linha, resetar e desativar ficam desabilitados e explicados", async () => {
    renderPagina();
    await screen.findByText("maria.admin");
    expect(screen.getByRole("button", { name: "Resetar senha de maria.admin" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Desativar maria.admin" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Editar maria.admin" })).toBeEnabled();
    expect(screen.getByText(NOTA_PROPRIA_CONTA)).toBeInTheDocument();
  });
});

describe("sessão contínua (modo TV)", () => {
  it("cria OPERADOR com a opção; para ADMIN ela fica travada e desmarcada", async () => {
    vi.mocked(criarUsuario).mockResolvedValue(detalheAdmin({ id: 21, username: "tv.loja", sessao_continua: true }));
    renderPagina();
    await screen.findByText("joao.silva");
    const dialogo = await abrirCriacao();
    const d = within(dialogo);
    const opcao = d.getByRole("checkbox", { name: "Sessão contínua (modo TV)" });

    await userEvent.click(opcao);
    expect(opcao).toBeChecked();
    await userEvent.click(d.getByRole("radio", { name: "ADMIN" }));
    expect(opcao).toBeDisabled();
    expect(opcao).not.toBeChecked();
    expect(d.getByText(/Só para OPERADOR/)).toBeInTheDocument();
    await userEvent.click(d.getByRole("radio", { name: "OPERADOR" }));
    expect(opcao).toBeChecked();

    await preencherCriacao(dialogo);
    await userEvent.click(d.getByRole("checkbox", { name: "Dashboard" }));
    await userEvent.click(d.getByRole("button", { name: "Criar usuário" }));
    expect(criarUsuario).toHaveBeenCalledWith(expect.objectContaining({ role: "OPERADOR", sessao_continua: true }));
  });

  it("editar: liga a opção e envia só ela; a lista mostra o selo Modo TV", async () => {
    vi.mocked(listarUsuarios).mockResolvedValue(paginaUsuarios([eu, { ...joao, sessao_continua: true }]));
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin({ modulos: ["DASHBOARD"] }));
    vi.mocked(atualizarUsuario).mockResolvedValue(detalheAdmin({ sessao_continua: true }));
    renderPagina();
    expect(await screen.findByText("Modo TV")).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "Editar joao.silva" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar usuário" }));
    await userEvent.click(await d.findByRole("checkbox", { name: "Sessão contínua (modo TV)" }));
    await userEvent.click(d.getByRole("button", { name: "Salvar alterações" }));

    expect(atualizarUsuario).toHaveBeenCalledWith(7, { sessao_continua: true });
  });
});

const ESTOQUISTA: PerfilAdmin = {
  id: 3,
  nome: "Estoquista",
  descricao: null,
  modulos: ["ESTOQUE"],
  abas: ["ESTOQUE.AVULSAS", "ESTOQUE.JUSTIFICATIVAS"],
  tela_inicial: "ESTOQUE.AVULSAS",
  usuarios: 2,
  created_at: "2026-10-29T13:00:00Z",
  updated_at: "2026-10-29T13:00:00Z",
};

describe("perfis de acesso", () => {
  it("cria perfil: marcar o módulo marca as sub-abas, e a tela inicial só oferece as marcadas", async () => {
    vi.mocked(criarPerfil).mockResolvedValue(ESTOQUISTA);
    renderPagina();
    await userEvent.click(screen.getByRole("tab", { name: "Perfis de acesso" }));
    expect(await screen.findByText("Nenhum perfil cadastrado.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Criar perfil" }));
    const d = within(await screen.findByRole("dialog", { name: "Criar perfil" }));
    await userEvent.type(d.getByLabelText("Nome do perfil"), "Estoquista");
    await userEvent.click(d.getByRole("checkbox", { name: "Estoque" }));
    expect(d.getByRole("checkbox", { name: "Saldos" })).toBeChecked();
    expect(d.getByRole("checkbox", { name: "Justificativas (dentro de Avulsas)" })).toBeChecked();
    for (const nome of ["Saldos", "Loja", "Entradas e saídas", "Balanço"]) {
      await userEvent.click(d.getByRole("checkbox", { name: nome }));
    }
    const tela = d.getByLabelText("Tela que abre no login");
    expect(within(tela).queryByRole("option", { name: "Estoque › Saldos" })).not.toBeInTheDocument();
    await userEvent.selectOptions(tela, "Estoque › Avulsas");
    await userEvent.click(d.getByRole("button", { name: "Gravar perfil" }));

    expect(criarPerfil).toHaveBeenCalledWith({
      nome: "Estoquista",
      descricao: null,
      modulos: ["ESTOQUE"],
      abas: ["ESTOQUE.AVULSAS", "ESTOQUE.JUSTIFICATIVAS"],
      tela_inicial: "ESTOQUE.AVULSAS",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Perfil Estoquista criado.");
  });

  it("desmarcar Avulsas tira Justificativas e a tela inicial que dependia dela", async () => {
    vi.mocked(listarPerfis).mockResolvedValue([ESTOQUISTA]);
    renderPagina();
    await userEvent.click(screen.getByRole("tab", { name: "Perfis de acesso" }));
    await userEvent.click(await screen.findByRole("button", { name: "Editar perfil Estoquista" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar perfil" }));
    expect(d.getByLabelText("Tela que abre no login")).toHaveValue("ESTOQUE.AVULSAS");

    await userEvent.click(d.getByRole("checkbox", { name: "Avulsas" }));
    expect(d.getByRole("checkbox", { name: "Justificativas (dentro de Avulsas)" })).not.toBeChecked();
    expect(d.getByLabelText("Tela que abre no login")).toHaveValue("");
  });

  it("excluir perfil em uso mostra a recusa do backend", async () => {
    vi.mocked(listarPerfis).mockResolvedValue([ESTOQUISTA]);
    vi.mocked(excluirPerfil).mockRejectedValue(
      new ApiError("O perfil tem 2 usuário(s). Troque o perfil deles antes de excluir.", "http", 409),
    );
    renderPagina();
    await userEvent.click(screen.getByRole("tab", { name: "Perfis de acesso" }));
    await userEvent.click(await screen.findByRole("button", { name: "Excluir perfil Estoquista" }));
    const d = within(await screen.findByRole("alertdialog"));
    await userEvent.click(d.getByRole("button", { name: "Excluir" }));
    expect(await d.findByText(/Troque o perfil deles antes de excluir/)).toBeInTheDocument();
  });

  it("editar usuário: escolher um perfil trava os módulos e envia só perfil_id", async () => {
    vi.mocked(listarPerfis).mockResolvedValue([ESTOQUISTA]);
    vi.mocked(obterUsuario).mockResolvedValue(detalheAdmin());
    vi.mocked(atualizarUsuario).mockResolvedValue(detalheAdmin({ perfil: { id: 3, nome: "Estoquista" } }));
    renderPagina();
    await userEvent.click(await screen.findByRole("button", { name: "Editar joao.silva" }));
    const d = within(await screen.findByRole("dialog", { name: "Editar usuário" }));
    const perfil = await d.findByLabelText("Perfil de acesso");
    await waitFor(() => expect(within(perfil).getByRole("option", { name: "Estoquista" })).toBeInTheDocument());

    await userEvent.selectOptions(perfil, "Estoquista");
    expect(d.getByRole("checkbox", { name: "Dashboard" })).toBeDisabled();
    expect(d.getByText(/Com o perfil Estoquista, os módulos vêm dele/)).toBeInTheDocument();
    await userEvent.click(d.getByRole("button", { name: "Salvar alterações" }));
    expect(atualizarUsuario).toHaveBeenCalledWith(7, { perfil_id: 3 });
  });
});
