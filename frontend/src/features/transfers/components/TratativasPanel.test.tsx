import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getTratativas, registrarTratativa } from "../../../services/controleTransferenciasService";
import { renderComSessao } from "../../../test/sessao";
import { TratativasPanel } from "./TratativasPanel";

vi.mock("../../../services/controleTransferenciasService", () => ({
  getTratativas: vi.fn(),
  registrarTratativa: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(getTratativas).mockResolvedValue([]);
});

describe("TratativasPanel", () => {
  it("registra quem verificou a transferência", async () => {
    vi.mocked(registrarTratativa).mockResolvedValue({
      id: 1,
      situacao: "RESOLVIDA",
      usuario_nome: "Teste",
      observacao: "Falta confirmada.",
      created_at: "2026-10-13T12:00:00Z",
    });
    const aoRegistrar = vi.fn();
    renderComSessao(<TratativasPanel id={7} aoRegistrar={aoRegistrar} />, { rota: "/transferencias?detalhe=7" });

    await userEvent.click(await screen.findByText("Resolvida"));
    await userEvent.type(screen.getByLabelText("O que foi verificado"), "Falta confirmada.");
    await userEvent.click(screen.getByRole("button", { name: "Registrar" }));

    await waitFor(() =>
      expect(registrarTratativa).toHaveBeenCalledWith(7, { situacao: "RESOLVIDA", observacao: "Falta confirmada." }),
    );
  });
});
