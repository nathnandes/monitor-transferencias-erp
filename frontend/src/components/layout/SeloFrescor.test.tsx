import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getFrescor } from "../../services/frescorService";
import type { Frescor, FrescorTipo } from "../../types/api";
import { pior, SeloFrescor } from "./SeloFrescor";

const minutosAtras = (min: number) => new Date(Date.now() - min * 60_000).toISOString();

function tipo(parcial: Partial<FrescorTipo> & Pick<FrescorTipo, "tipo">): FrescorTipo {
  return { intervalo_segundos: 300, ultima_conclusao: minutosAtras(3), limite_segundos: 1800, situacao: "EM_DIA", ...parcial };
}

function responder(tipos: FrescorTipo[]) {
  const resposta: Frescor = { gerado_em: new Date().toISOString(), tipos };
  vi.mocked(getFrescor).mockResolvedValue(resposta);
}

afterEach(() => {
  vi.mocked(getFrescor).mockReset();
});

describe("SeloFrescor", () => {
  it("mostra há quanto tempo o ERP foi sincronizado", async () => {
    responder([tipo({ tipo: "transferencias" })]);
    render(<SeloFrescor fontes={["transferencias"]} />);
    expect(await screen.findByText("Dados do ERP há 3 min")).toBeInTheDocument();
  });

  it("fica vermelho quando a sincronização está parada", async () => {
    responder([
      tipo({ tipo: "estoque" }),
      tipo({ tipo: "precos", situacao: "PARADA", ultima_conclusao: minutosAtras(180) }),
    ]);
    render(<SeloFrescor fontes={["estoque", "precos"]} />);
    const selo = await screen.findByText("Sincronização de preços parada: dados há 3 h");
    expect(selo).toHaveClass("text-critico-texto");
  });

  it("ignora as fontes que não são da tela", async () => {
    responder([tipo({ tipo: "vendas" }), tipo({ tipo: "estoque", situacao: "PARADA" })]);
    render(<SeloFrescor fontes={["vendas"]} />);
    expect(await screen.findByText("Dados do ERP há 3 min")).toBeInTheDocument();
  });

  it("some quando nenhuma fonte da tela é sincronizada", async () => {
    responder([tipo({ tipo: "vendas", situacao: "PARADA" })]);
    const { container } = render(<SeloFrescor fontes={["estoque"]} />);
    await vi.waitFor(() => expect(getFrescor).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("pior", () => {
  it("escolhe a mais grave e, no empate, a mais antiga", () => {
    const antiga = tipo({ tipo: "estoque", ultima_conclusao: minutosAtras(10) });
    const nova = tipo({ tipo: "precos", ultima_conclusao: minutosAtras(1) });
    const atrasada = tipo({ tipo: "vendas", situacao: "ATRASADA" });
    expect(pior([nova, antiga])).toBe(antiga);
    expect(pior([antiga, atrasada, nova])).toBe(atrasada);
    expect(pior([])).toBeNull();
  });
});
