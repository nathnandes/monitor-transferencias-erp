import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getLimites, salvarLimites } from "../../../services/controleTransferenciasService";
import { LimitesPendenciaPanel } from "./LimitesPendenciaPanel";

vi.mock("../../../services/controleTransferenciasService", () => ({
  getLimites: vi.fn(),
  salvarLimites: vi.fn(),
}));

const PADRAO = { horas_atencao: 24, horas_critico: 48, definido_por: null, atualizado_em: null };

beforeEach(() => {
  vi.mocked(getLimites).mockResolvedValue(PADRAO);
  vi.mocked(salvarLimites).mockResolvedValue({ ...PADRAO, horas_atencao: 12, definido_por: "Admin" });
});

describe("LimitesPendenciaPanel", () => {
  it("o admin muda a atenção e salva", async () => {
    const aoSalvar = vi.fn();
    render(<LimitesPendenciaPanel ehAdmin aoSalvar={aoSalvar} />);
    const atencao = await screen.findByLabelText("Atenção após");
    expect(atencao).toHaveValue(24);
    expect(screen.getByText("Padrão do sistema (24 h e 48 h).")).toBeInTheDocument();

    await userEvent.clear(atencao);
    await userEvent.type(atencao, "12");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(salvarLimites).toHaveBeenCalledWith({ horas_atencao: 12, horas_critico: 48 }));
    expect(aoSalvar).toHaveBeenCalled();
  });

  it("não deixa a atenção passar do crítico", async () => {
    render(<LimitesPendenciaPanel ehAdmin aoSalvar={vi.fn()} />);
    const atencao = await screen.findByLabelText("Atenção após");
    await userEvent.clear(atencao);
    await userEvent.type(atencao, "60");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("atenção menor que o crítico");
    expect(salvarLimites).not.toHaveBeenCalled();
  });

  it("quem não é admin só vê", async () => {
    render(<LimitesPendenciaPanel ehAdmin={false} aoSalvar={vi.fn()} />);
    expect(await screen.findByLabelText("Crítico após")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();
  });
});
