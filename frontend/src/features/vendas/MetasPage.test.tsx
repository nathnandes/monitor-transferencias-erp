

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getEmpresas } from "../../services/empresasService";
import {
  excluirMeta,
  getMetas,
  getProgressoMetas,
  getVendedoresMeta,
  salvarMarcos,
  salvarMeta,
} from "../../services/metasService";
import { authFalso, renderComSessao, usuarioTeste } from "../../test/sessao";
import type { ConfiguracaoMetas, Meta, ProgressoMetas } from "../../types/api";
import { MetasPage, TITULO_METAS } from "./MetasPage";

vi.mock("../../services/metasService", () => ({
  getMetas: vi.fn(),
  getProgressoMetas: vi.fn(),
  getVendedoresMeta: vi.fn(),
  salvarMeta: vi.fn(),
  excluirMeta: vi.fn(),
  salvarMarcos: vi.fn(),
}));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));

function meta(parcial: Partial<Meta> = {}): Meta {
  return {
    id: 1,
    nivel: "EMPRESA",
    empresa_id: 10,
    id_vendedor: null,
    alvo: "MATRIZ",
    periodo: "MES",
    referencia: null,
    valor: "500000.00",
    atualizado_por: "Admin",
    atualizado_em: "2026-11-03T12:00:00Z",
    ...parcial,
  };
}

const CONFIG: ConfiguracaoMetas = { metas: [meta(), meta({ id: 2, periodo: "DIA", referencia: "2026-12-24", valor: "30000.00" })], marcos: [100] };

const PROGRESSO: ProgressoMetas = {
  dia: "2026-11-03",
  itens: [
    {
      meta_id: 1,
      nivel: "EMPRESA",
      alvo: "MATRIZ",
      periodo: "MES",
      rotulo_periodo: "novembro/2026",
      inicio: "2026-11-01",
      fim: "2026-11-30",
      valor: "500000.00",
      realizado: "125000.00",
      percentual: "25.0",
      especifica: false,
    },
  ],
};

const admin = () => authFalso(["VENDAS"], usuarioTeste({ role: "ADMIN" }));
const operador = () => authFalso(["VENDAS"], usuarioTeste({ role: "OPERADOR" }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getMetas).mockResolvedValue(CONFIG);
  vi.mocked(getProgressoMetas).mockResolvedValue(PROGRESSO);
  vi.mocked(getVendedoresMeta).mockResolvedValue([{ id_erp: "V9", nome: "CAMILA" }]);
  vi.mocked(getEmpresas).mockResolvedValue([
    { id: 10, codigo: "1", nome: "MATRIZ", id_erp: "1", ativo: true, created_at: "", updated_at: "" } as never,
  ]);
});

describe("MetasPage", () => {
  it("mostra o andamento com a barra e as metas cadastradas", async () => {
    renderComSessao(<MetasPage />, { auth: operador() });
    expect(screen.getByRole("heading", { level: 1, name: TITULO_METAS })).toBeInTheDocument();
    const barra = await screen.findByRole("progressbar", { name: "MATRIZ: 25% da meta" });
    expect(barra).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText(/R\$ 125\.000,00 de R\$ 500\.000,00/)).toBeInTheDocument();

    const tabela = await screen.findByRole("table", { name: "Metas cadastradas" });
    expect(within(tabela).getByText("Vale sempre")).toBeInTheDocument();
    expect(within(tabela).getByText("Só 24/12/2026")).toBeInTheDocument();

    expect(screen.queryByRole("form", { name: "Nova meta" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Excluir meta/ })).not.toBeInTheDocument();
  });

  it("ADMIN cadastra a meta de um vendedor só para um mês", async () => {
    vi.mocked(salvarMeta).mockResolvedValue(CONFIG);
    renderComSessao(<MetasPage />, { auth: admin() });
    const form = await screen.findByRole("form", { name: "Nova meta" });

    await userEvent.selectOptions(within(form).getByLabelText("Para"), "VENDEDOR");
    await userEvent.selectOptions(await within(form).findByLabelText("Vendedor"), "V9");
    await userEvent.type(within(form).getByLabelText("Valor (R$)"), "45.000,50");
    await userEvent.click(within(form).getByRole("checkbox", { name: /período específico/ }));
    await userEvent.type(within(form).getByLabelText("Data do período específico"), "2026-12-10");
    await userEvent.click(within(form).getByRole("button", { name: "Salvar meta" }));

    await waitFor(() =>
      expect(salvarMeta).toHaveBeenCalledWith({
        nivel: "VENDEDOR",
        periodo: "MES",
        valor: "45000.50",
        empresa_id: null,
        id_vendedor: "V9",
        referencia: "2026-12-10",
      }),
    );
    expect(await screen.findByText("Meta salva.")).toBeInTheDocument();
  });

  it("ADMIN muda os marcos e exclui uma meta", async () => {
    vi.mocked(salvarMarcos).mockResolvedValue({ ...CONFIG, marcos: [50, 100] });
    vi.mocked(excluirMeta).mockResolvedValue();
    renderComSessao(<MetasPage />, { auth: admin() });

    const marcos = await screen.findByLabelText(/Avisar no Telegram/);
    await userEvent.clear(marcos);
    await userEvent.type(marcos, "50, 100");
    await userEvent.click(screen.getByRole("button", { name: "Salvar marcos" }));
    expect(salvarMarcos).toHaveBeenCalledWith([50, 100]);

    const [primeira] = screen.getAllByRole("button", { name: "Excluir meta de MATRIZ" });
    await userEvent.click(primeira!);
    await userEvent.click(await screen.findByRole("button", { name: "Excluir" }));
    expect(excluirMeta).toHaveBeenCalledWith(1);
    expect(await screen.findByText("Meta de MATRIZ excluída.")).toBeInTheDocument();
  });
});
