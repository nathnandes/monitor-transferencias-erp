

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  excluirModeloMensagemAvulsa,
  listarModelosMensagemAvulsa,
  salvarModeloMensagemAvulsa,
} from "../../../services/alertasConfigService";
import type { ModeloMensagemAvulsa } from "../../../types/api";
import { ModelosSalvos } from "./ModelosSalvos";

vi.mock("../../../services/alertasConfigService", () => ({
  listarModelosMensagemAvulsa: vi.fn(),
  salvarModeloMensagemAvulsa: vi.fn(),
  excluirModeloMensagemAvulsa: vi.fn(),
}));

function modelo(id: number, nome: string, texto: string): ModeloMensagemAvulsa {
  return { id, nome, texto, atualizado_por: "Admin", updated_at: "2026-11-05T12:00:00Z" };
}

const RESUMO = modelo(1, "Resumo das 18h", "Líquido: {faturamento_liquido}");

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listarModelosMensagemAvulsa).mockResolvedValue([RESUMO]);
  vi.mocked(salvarModeloMensagemAvulsa).mockResolvedValue([modelo(2, "Bom dia", "Oi"), RESUMO]);
  vi.mocked(excluirModeloMensagemAvulsa).mockResolvedValue([]);
});

describe("ModelosSalvos", () => {
  it("escolher um modelo preenche o texto", async () => {
    const aoUsar = vi.fn();
    const usuario = userEvent.setup();
    render(<ModelosSalvos texto="" aoUsar={aoUsar} />);

    await screen.findByRole("option", { name: "Resumo das 18h" });
    await usuario.selectOptions(screen.getByLabelText("Modelo salvo"), "Resumo das 18h");
    expect(aoUsar).toHaveBeenCalledWith("Líquido: {faturamento_liquido}");
  });

  it("salva o texto atual com o nome e seleciona o modelo salvo", async () => {
    const usuario = userEvent.setup();
    render(<ModelosSalvos texto="Oi" aoUsar={vi.fn()} />);

    await usuario.click(screen.getByRole("button", { name: "Salvar como modelo" }));
    await usuario.type(screen.getByLabelText("Nome do modelo"), "Bom dia");
    await usuario.click(screen.getByRole("button", { name: "Salvar modelo" }));

    expect(salvarModeloMensagemAvulsa).toHaveBeenCalledWith("Bom dia", "Oi");
    expect(await screen.findByRole("status")).toHaveTextContent('Modelo "Bom dia" salvo.');
    expect(screen.getByLabelText("Modelo salvo")).toHaveDisplayValue("Bom dia");
  });

  it("não salva sem texto ou sem nome", async () => {
    const usuario = userEvent.setup();
    const { rerender } = render(<ModelosSalvos texto="" aoUsar={vi.fn()} />);

    await usuario.click(screen.getByRole("button", { name: "Salvar como modelo" }));
    await usuario.click(screen.getByRole("button", { name: "Salvar modelo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Escreva a mensagem antes de salvar.");

    rerender(<ModelosSalvos texto="Oi" aoUsar={vi.fn()} />);
    await usuario.click(screen.getByRole("button", { name: "Salvar modelo" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Dê um nome ao modelo.");
    expect(salvarModeloMensagemAvulsa).not.toHaveBeenCalled();
  });

  it("exclui o modelo escolhido depois de confirmar", async () => {
    const usuario = userEvent.setup();
    render(<ModelosSalvos texto="" aoUsar={vi.fn()} />);

    await screen.findByRole("option", { name: "Resumo das 18h" });
    await usuario.selectOptions(screen.getByLabelText("Modelo salvo"), "Resumo das 18h");
    await usuario.click(screen.getByRole("button", { name: "Excluir modelo Resumo das 18h" }));
    await usuario.click(screen.getByRole("button", { name: "Excluir" }));

    expect(excluirModeloMensagemAvulsa).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.queryByRole("option", { name: "Resumo das 18h" })).toBeNull());
  });
});
