import { act, cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getResumoVendas } from "../../services/vendasService";
import { resumoVendas, totaisVendas } from "../../test/factories";
import { authFalso, renderComSessao } from "../../test/sessao";
import { INTERVALO_VENDAS_TV_MS, VendasTvPage } from "./VendasTvPage";

vi.mock("../../services/vendasService", () => ({ getResumoVendas: vi.fn() }));

const auth = () => authFalso(["VENDAS"]);
const indicador = (rotulo: string) => screen.getByRole("heading", { name: rotulo }).closest("article")!;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.history.replaceState(null, "", "/vendas/tv?empresa=03&periodo=mes");
  vi.mocked(getResumoVendas).mockResolvedValue(resumoVendas());
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("VendasTvPage", () => {
  it("mostra faturamento, ticket, notas, vendedores, lojas e canais no filtro da URL", async () => {
    renderComSessao(<VendasTvPage />, { auth: auth(), rota: "/vendas/tv" });


    expect(await within(indicador("Faturamento líquido")).findByText("R$ 120.000,00")).toBeInTheDocument();
    expect(within(indicador("Faturamento líquido")).getByText("▲ 20%")).toBeInTheDocument();
    expect(within(indicador("Faturamento líquido")).getByText("Bruto R$ 125.430,90 · devoluções R$ 5.430,90")).toBeInTheDocument();
    expect(indicador("Ticket médio")).toHaveTextContent("R$ 418,10");
    expect(within(indicador("Notas")).getByText("300")).toBeInTheDocument();

    const vendedores = within(screen.getByRole("region", { name: "Melhores vendedores" })).getAllByRole("listitem");
    expect(vendedores).toHaveLength(3);
    expect(vendedores[0]).toHaveTextContent("1º");
    expect(vendedores[0]).toHaveTextContent("Maria da Silva Souza");
    expect(vendedores[0]).toHaveTextContent("R$ 80.000,00");
    expect(vendedores[2]).toHaveTextContent("Vendedor 16055");

    expect(screen.getByRole("region", { name: "Lojas" })).toHaveTextContent("1 · Empresa 1");
    const canais = screen.getByRole("region", { name: "Canais" });
    expect(canais).toHaveTextContent("Faturamento");
    expect(canais).toHaveTextContent("Balcão");

    const [params] = vi.mocked(getResumoVendas).mock.calls[0]!;
    expect(params).toMatchObject({ empresa: "03" });
    expect(params?.data_inicial).toMatch(/-01$/);
    expect(screen.getByRole("link", { name: /Sair do modo TV/ })).toHaveAttribute("href", "/vendas?empresa=03&periodo=mes");
  });

  it("com filtro de canal mostra o faturamento bruto", async () => {
    window.history.replaceState(null, "", "/vendas/tv?canal=balcao");
    vi.mocked(getResumoVendas).mockResolvedValue(
      resumoVendas({ totais: totaisVendas("25430.90", 250, null), comparacao: null, formas_pagamento: null }),
    );
    renderComSessao(<VendasTvPage />, { auth: auth(), rota: "/vendas/tv" });

    await screen.findByRole("heading", { name: "Faturamento" });
    expect(indicador("Faturamento")).toHaveTextContent("R$ 25.430,90");
    expect(indicador("Faturamento")).toHaveTextContent("Bruto: devoluções não têm canal");
    expect(vi.mocked(getResumoVendas).mock.calls[0]![0]).toMatchObject({ canal: "balcao" });
    expect(screen.getByText(/· balcão$/)).toBeInTheDocument();
  });

  it("atualiza sozinho a cada minuto e, sem conexão, mantém os números e avisa", async () => {
    renderComSessao(<VendasTvPage />, { auth: auth(), rota: "/vendas/tv" });
    await within(indicador("Faturamento líquido")).findByText("R$ 120.000,00");
    expect(getResumoVendas).toHaveBeenCalledTimes(1);

    vi.mocked(getResumoVendas).mockRejectedValue(new Error("rede"));
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_VENDAS_TV_MS));
    expect(getResumoVendas).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole("alert")).toHaveTextContent("Sem conexão com o servidor");
    expect(within(indicador("Faturamento líquido")).getByText("R$ 120.000,00")).toBeInTheDocument();
  });
});
