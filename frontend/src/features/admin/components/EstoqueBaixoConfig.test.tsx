

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getEstoqueBaixo,
  getSituacaoEstoqueBaixo,
  salvarEstoqueBaixo,
} from "../../../services/estoqueBaixoService";
import type { ParametrosEstoqueBaixo } from "../../../types/api";
import { EstoqueBaixoConfig } from "./EstoqueBaixoConfig";

vi.mock("../../../services/estoqueBaixoService", () => ({
  getEstoqueBaixo: vi.fn(),
  getSituacaoEstoqueBaixo: vi.fn(),
  salvarEstoqueBaixo: vi.fn(),
}));

const PADRAO: ParametrosEstoqueBaixo = {
  configurado: false,
  ativo: false,
  dias_cobertura: 7,
  dias_por_empresa: {},
  janela_dias: 30,
  horarios: ["08:00"],
  ultima_execucao: null,
  atualizado_por: null,
  atualizado_em: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getEstoqueBaixo).mockResolvedValue(PADRAO);
  vi.mocked(getSituacaoEstoqueBaixo).mockResolvedValue({
    lojas: [
      {
        empresa_id: 10,
        codigo: "1",
        nome: "MATRIZ",
        dias: 7,
        total: 3,
        produtos: [
          {
            id_produto: "123",
            id_subproduto: "123",
            descricao: "LONA AZUL",
            disponivel: "2",
            venda_media_diaria: "1.5",
            minimo: "10.5",
          },
        ],
      },
    ],
  });
});

describe("EstoqueBaixoConfig", () => {
  it("mostra o que está baixo antes de salvar, com os valores padrão", async () => {
    render(<EstoqueBaixoConfig aoSalvar={vi.fn()} />);
    const lista = await screen.findByRole("region", { name: "Abaixo do mínimo agora" });
    expect(within(lista).getByText(/MATRIZ: 3 produtos/)).toBeInTheDocument();
    expect(within(lista).getByText(/LONA AZUL: tem 2, mínimo 10,5/)).toBeInTheDocument();
    expect(within(lista).getByText("… e mais 2")).toBeInTheDocument();
    expect(await screen.findByText(/Ainda não configurado/)).toBeInTheDocument();
  });

  it("salva dias, horários e os dias de uma loja", async () => {
    const aoSalvar = vi.fn();
    vi.mocked(salvarEstoqueBaixo).mockResolvedValue({ ...PADRAO, configurado: true, ativo: true });
    render(<EstoqueBaixoConfig aoSalvar={aoSalvar} />);
    const dias = await screen.findByLabelText("Dias de venda em estoque");
    await userEvent.clear(dias);
    await userEvent.type(dias, "15");
    const horarios = screen.getByLabelText("Horários do resumo");
    await userEvent.clear(horarios);
    await userEvent.type(horarios, "8h, 14:30");
    await userEvent.type(await screen.findByLabelText("Dias de venda da loja MATRIZ"), "30");
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() =>
      expect(salvarEstoqueBaixo).toHaveBeenCalledWith({
        ativo: true,
        dias_cobertura: 15,
        janela_dias: 30,
        horarios: ["08:00", "14:30"],
        dias_por_empresa: { "10": 30 },
      }),
    );
    expect(aoSalvar).toHaveBeenCalledWith("Aviso de estoque baixo salvo.");
  });
});
