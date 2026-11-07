

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listarAtividades } from "../../services/atividadesService";
import { authFalso, renderComSessao, usuarioTeste } from "../../test/sessao";
import type { PaginaAtividades } from "../../types/api";
import { AdminHistoricoPage, TITULO_ADMIN_HISTORICO } from "./AdminHistoricoPage";

vi.mock("../../services/atividadesService", async (original) => ({
  ...(await original<typeof import("../../services/atividadesService")>()),
  listarAtividades: vi.fn(),
}));

function pagina(parcial: Partial<PaginaAtividades> = {}): PaginaAtividades {
  return {
    total: 2,
    pagina: 1,
    tamanho_pagina: 50,
    total_paginas: 1,
    tipos: [
      { chave: "login", nome: "Entrada no sistema" },
      { chave: "usuarios_alterados", nome: "Usuários alterados" },
    ],
    itens: [
      {
        id: 2,
        tipo: "usuarios_alterados",
        tipo_nome: "Usuários alterados",
        usuario_nome: "Admin",
        ip: "127.0.0.1",
        resumo: "Admin alterou o usuário maria",
        detalhe: "Campos alterados: nome_exibicao",
        ocorrida_em: "2026-11-03T12:00:00Z",
      },
      {
        id: 1,
        tipo: "login",
        tipo_nome: "Entrada no sistema",
        usuario_nome: "Maria",
        ip: null,
        resumo: "Maria entrou no sistema",
        detalhe: null,
        ocorrida_em: "2026-11-03T11:00:00Z",
      },
    ],
    ...parcial,
  };
}

const auth = () => authFalso(["ADMINISTRACAO"], usuarioTeste({ role: "ADMIN" }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listarAtividades).mockResolvedValue(pagina());
});

describe("AdminHistoricoPage", () => {
  it("lista as atividades com o detalhe e o IP", async () => {
    renderComSessao(<AdminHistoricoPage />, { auth: auth() });
    expect(screen.getByRole("heading", { level: 1, name: TITULO_ADMIN_HISTORICO })).toBeInTheDocument();
    expect(await screen.findByText("Admin alterou o usuário maria")).toBeInTheDocument();
    expect(screen.getByText("Campos alterados: nome_exibicao")).toBeInTheDocument();
    expect(screen.getByText("127.0.0.1")).toBeInTheDocument();
    expect(screen.getByText("Maria entrou no sistema")).toBeInTheDocument();
  });

  it("filtra por tipo na hora e por quem ao enviar", async () => {
    renderComSessao(<AdminHistoricoPage />, { auth: auth() });
    await screen.findByText("Maria entrou no sistema");

    await userEvent.selectOptions(screen.getByLabelText("Tipo"), "login");
    await waitFor(() =>
      expect(listarAtividades).toHaveBeenLastCalledWith({ tipo: "login", usuario: "" }, 1, expect.anything()),
    );

    await userEvent.type(screen.getByLabelText("Quem"), "mar");
    await userEvent.click(screen.getByRole("button", { name: "Filtrar" }));
    await waitFor(() =>
      expect(listarAtividades).toHaveBeenLastCalledWith({ tipo: "login", usuario: "mar" }, 1, expect.anything()),
    );
  });

  it("mostra o vazio quando nada atende aos filtros", async () => {
    vi.mocked(listarAtividades).mockResolvedValue(pagina({ total: 0, total_paginas: 0, itens: [] }));
    renderComSessao(<AdminHistoricoPage />, { auth: auth() });
    expect(await screen.findByText("Nenhuma atividade")).toBeInTheDocument();
  });
});
