import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getEmpresas } from "../../services/empresasService";
import { getParcelas, getResumoFinanceiro } from "../../services/financeiroService";
import { ApiError } from "../../services/apiClient";
import { paginaParcelas, resumoFinanceiro } from "../../test/factories";
import { authFalso, renderComSessao } from "../../test/sessao";
import { FinanceiroPage, TITULO_FINANCEIRO } from "./FinanceiroPage";

vi.mock("../../services/financeiroService", () => ({
  getResumoFinanceiro: vi.fn(),
  getParcelas: vi.fn(),
}));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));

const auth = () => authFalso(["FINANCEIRO"]);
const cartao = (rotulo: string) =>
  screen.getByRole("heading", { name: rotulo }).closest("article")!;

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/financeiro");
  vi.mocked(getEmpresas).mockResolvedValue([]);
  vi.mocked(getResumoFinanceiro).mockResolvedValue(resumoFinanceiro());
  vi.mocked(getParcelas).mockResolvedValue(paginaParcelas());
});

describe("FinanceiroPage", () => {
  it("mostra o vendido, o pago e o pendente das vendas do período", async () => {
    renderComSessao(<FinanceiroPage />, { auth: auth(), rota: "/financeiro" });

    expect(
      screen.getByRole("heading", { level: 1, name: TITULO_FINANCEIRO }),
    ).toBeInTheDocument();
    await screen.findByText("R$ 100.000,00");
    expect(cartao("Vendido")).toHaveTextContent("R$ 100.000,00");
    expect(cartao("Vendido")).toHaveTextContent("200 parcelas");
    expect(cartao("Já pago")).toHaveTextContent("R$ 90.000,00");
    expect(cartao("Já pago")).toHaveTextContent("90,0% do vendido");
    expect(cartao("Pendente")).toHaveTextContent("R$ 10.000,00");

    expect(vi.mocked(getResumoFinanceiro).mock.calls.at(-1)![0]).toMatchObject({
      data_inicial: expect.any(String),
    });
    const formas = screen
      .getByRole("heading", { name: "Vendido por forma" })
      .closest("section")!;
    expect(within(formas).getByTitle("PIX TEF")).toHaveTextContent("Pix tef");
    expect(within(formas).getByText("60,0%")).toBeInTheDocument();
  });

  it("mostra o recebido no período: vendas do período, boletos e outros", async () => {
    renderComSessao(<FinanceiroPage />, { auth: auth(), rota: "/financeiro" });

    await screen.findByText("R$ 95.000,00");
    expect(cartao("Recebido")).toHaveTextContent(
      "190 parcelas · juros R$ 12,50",
    );
    expect(cartao("Das vendas do período")).toHaveTextContent("R$ 90.000,00");
    expect(cartao("De boletos")).toHaveTextContent("R$ 4.000,00");
    expect(cartao("Outros a prazo de antes")).toHaveTextContent("R$ 1.000,00");
    const lista = screen.getByRole("list", {
      name: "Recebido por forma de pagamento",
    });
    expect(
      within(lista)
        .getAllByRole("listitem")
        .map((f) => f.textContent),
    ).toEqual([
      "Pix tef120 parc.R$ 60.000,00",
      "Cartao credito tef60 parc.R$ 30.000,00",
      "Boleto banco exemplo10 parc.R$ 5.000,00",
    ]);
  });

  it("período sem parcelas mostra os painéis vazios", async () => {
    const vazio = resumoFinanceiro();
    vi.mocked(getResumoFinanceiro).mockResolvedValue({
      ...vazio,
      vendas: {
        valor: "0",
        valor_pago: "0",
        valor_pendente: "0",
        parcelas: 0,
        formas: [],
      },
      recebidos: {
        total: "0",
        de_vendas_anteriores: "0",
        de_boletos: "0",
        das_vendas_do_periodo: "0",
        outros_anteriores: "0",
        juros: "0",
        titulos: 0,
        formas: [],
      },
    });
    renderComSessao(<FinanceiroPage />, { auth: auth(), rota: "/financeiro" });

    await waitFor(() =>
      expect(screen.getAllByText(/Nada no período/)).toHaveLength(2),
    );
  });

  it("falha na busca mostra o erro nos painéis", async () => {
    vi.mocked(getResumoFinanceiro).mockRejectedValue(
      new ApiError("Falha de rede", "rede"),
    );
    renderComSessao(<FinanceiroPage />, { auth: auth(), rota: "/financeiro" });

    expect(
      (await screen.findAllByText(/Falha de rede/)).length,
    ).toBeGreaterThan(0);
  });

  it("lista parcela por parcela e filtra as pendentes pelo dia do pagamento", async () => {
    const user = userEvent.setup();
    renderComSessao(<FinanceiroPage />, { auth: auth(), rota: "/financeiro" });

    const tabela = await screen.findByRole("table", { name: "Parcelas, uma a uma" });
    const linhas = within(tabela).getAllByRole("row");
    expect(linhas).toHaveLength(3);
    expect(linhas[1]).toHaveTextContent("900123");
    expect(linhas[1]).toHaveTextContent("05/11/2026");
    expect(linhas[1]).toHaveTextContent("Paga");
    expect(linhas[2]).toHaveTextContent("R$ 150,00");
    expect(linhas[2]).toHaveTextContent("Pendente");
    expect(
      screen.getByText(/2 parcelas · valor R\$ 350,00 · pago R\$ 200,00 · pendente R\$ 150,00/),
    ).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Situação"), "pendentes");
    await user.selectOptions(screen.getByLabelText("Período pelo dia"), "pagamento");
    await waitFor(() =>
      expect(getParcelas).toHaveBeenLastCalledWith(
        expect.objectContaining({ situacao: "pendentes", data_por: "pagamento", pagina: 1 }),
        expect.anything(),
      ),
    );
  });
});
