import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getPrazos, salvarPrazos } from "../../../services/controleTransferenciasService";
import type { RotaControle } from "../../../types/api";
import { PrazosRotaPanel } from "./PrazosRotaPanel";

vi.mock("../../../services/controleTransferenciasService", () => ({
  getPrazos: vi.fn(),
  salvarPrazos: vi.fn(),
}));

const loja = (codigo: string) => ({ id: Number(codigo), codigo, nome: `Loja ${codigo}` });

function rota(origem: string, destino: string): RotaControle {
  return {
    origem: loja(origem),
    destino: loja(destino),
    prazo_horas: 24,
    prazo_padrao: true,
    enviadas: 1,
    recebidas: 1,
    pendentes: 0,
    fora_do_prazo: 0,
    divergentes: 0,
    valor_enviado: "10.00",
    tempo_medio_horas: 5,
  };
}

beforeEach(() => {
  vi.mocked(getPrazos).mockResolvedValue({ prazo_padrao_horas: 24, prazos: [] });
  vi.mocked(salvarPrazos).mockResolvedValue({ prazo_padrao_horas: 24, prazos: [] });
});

describe("PrazosRotaPanel", () => {
  it("salva a edição mesmo que a rota saia da lista na atualização automática", async () => {
    const props = { padrao: 24, ehAdmin: true, aoSalvar: vi.fn() };
    const { rerender } = render(<PrazosRotaPanel rotas={[rota("1", "2")]} {...props} />);
    await userEvent.type(await screen.findByLabelText(/1 → 2/), "48");


    rerender(<PrazosRotaPanel rotas={[]} {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Salvar (1)" }));

    await waitFor(() => expect(salvarPrazos).toHaveBeenCalledWith([{ origem: "1", destino: "2", horas: 48 }]));
    expect(await screen.findByText("Prazos salvos.")).toBeInTheDocument();
  });
});
