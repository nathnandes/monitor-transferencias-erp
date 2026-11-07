import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { hojeNoFuso } from "../../lib/periodo";
import { getHealthLive } from "../../services/dashboardService";
import { getEmpresas } from "../../services/empresasService";
import { getTransferencia, getTransferencias } from "../../services/transferenciasService";
import { detalhe, pagina, transferencia } from "../../test/factories";
import { authFalso, renderComSessao } from "../../test/sessao";
import type { Empresa } from "../../types/api";
import { AVISO_SEM_EMPRESAS, TransferenciasPage } from "./TransferenciasPage";


vi.mock("../../services/dashboardService", () => ({ getHealthLive: vi.fn(), getResumoDashboard: vi.fn() }));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));
vi.mock("../../services/transferenciasService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/transferenciasService")>()),
  getTransferencias: vi.fn(),
  getTransferencia: vi.fn(),
}));

const empresaDemo: Empresa = {
  id: 1,
  codigo: "01",
  nome: "Empresa 01",
  bairro: null,
  id_erp: "DEMO-EMP-01",
  ativo: true,
  ambiente: "development",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

const ultimaChamada = () => vi.mocked(getTransferencias).mock.calls.at(-1)!;

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
  vi.mocked(getHealthLive).mockResolvedValue({ status: "ok", app: "erp-automation", env: "development" });
  vi.mocked(getEmpresas).mockResolvedValue([empresaDemo]);
  vi.mocked(getTransferencias).mockImplementation(async (_filtros, p = 1) =>
    pagina([transferencia({ id: 100 + p, id_erp: `DEMO-TRF-P${p}` })], {
      total: 45,
      total_paginas: 3,
      pagina: p,
    }),
  );
});

describe("TransferenciasPage — consulta", () => {
  it("aplica filtros só no botão, pagina preservando filtros e sincroniza a URL", async () => {
    renderComSessao(<TransferenciasPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Transferências" })).toBeInTheDocument();
    expect(await screen.findByText("DEMO-TRF-P1")).toBeInTheDocument();
    const chamadasIniciais = vi.mocked(getTransferencias).mock.calls.length;

    await userEvent.selectOptions(await screen.findByLabelText("Saiu de"), "01");
    expect(getTransferencias).toHaveBeenCalledTimes(chamadasIniciais);

    await userEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));

    const hoje = hojeNoFuso();
    await waitFor(() =>
      expect(ultimaChamada()[0]).toEqual({ empresa_origem: "01", data_inicial: hoje, data_final: hoje }),
    );
    expect(ultimaChamada()[1]).toBe(1);
    expect(window.location.search).toBe("?empresa_origem=01");

    await userEvent.click(await screen.findByRole("button", { name: "Próxima" }));
    await waitFor(() => expect(ultimaChamada()[1]).toBe(2));
    expect(ultimaChamada()[0]).toMatchObject({ empresa_origem: "01" });
    expect(window.location.search).toBe("?empresa_origem=01&pagina=2");
    expect(await screen.findByText("DEMO-TRF-P2")).toBeInTheDocument();


    const antes = vi.mocked(getTransferencias).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    await waitFor(() => expect(window.location.search).toBe("?empresa_origem=01"));
    await waitFor(() => expect(ultimaChamada()[1]).toBe(1));
    const depois = vi.mocked(getTransferencias).mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    expect(vi.mocked(getTransferencias).mock.calls.length).toBe(depois);
    expect(depois).toBe(antes + 1);
  });

  it("abre o detalhe, fecha e volta à tabela com filtros e página preservados", async () => {
    window.history.replaceState(null, "", "/?status=PENDENTE&pagina=2");
    vi.mocked(getTransferencia).mockResolvedValue(detalhe({ id: 102, id_erp: "DEMO-TRF-P2" }));
    renderComSessao(<TransferenciasPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Ver detalhes da transferência DEMO-TRF-P2" }));
    const dialogo = await screen.findByRole("dialog", { name: "Transferência #102" });
    expect(await within(dialogo).findByText("Produto A")).toBeInTheDocument();
    expect(window.location.search).toBe("?status=PENDENTE&pagina=2&detalhe=102");
    const buscasTabela = vi.mocked(getTransferencias).mock.calls.length;

    await userEvent.click(within(dialogo).getByRole("button", { name: "Fechar detalhes" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(window.location.search).toBe("?status=PENDENTE&pagina=2");
    expect(screen.getByLabelText("Situação")).toHaveValue("PENDENTE");
    expect(screen.getByText("DEMO-TRF-P2")).toBeInTheDocument();

    expect(vi.mocked(getTransferencias).mock.calls.length).toBe(buscasTabela);
  });

  it("abre o detalhe direto pelo link (?detalhe=)", async () => {
    window.history.replaceState(null, "", "/?detalhe=102");
    vi.mocked(getTransferencia).mockResolvedValue(detalhe({ id: 102 }));
    renderComSessao(<TransferenciasPage />);
    expect(await screen.findByRole("dialog", { name: "Transferência #102" })).toBeInTheDocument();
    expect(getTransferencia).toHaveBeenCalledWith(102, expect.any(AbortSignal));
  });
});

describe("TransferenciasPage — sem o módulo DASHBOARD", () => {
  it("não chama /empresas (daria 403) e explica o filtro sem empresas", async () => {
    renderComSessao(<TransferenciasPage />, { auth: authFalso(["TRANSFERENCIAS"]) });
    expect(await screen.findByText("DEMO-TRF-P1")).toBeInTheDocument();
    expect(screen.getByText(AVISO_SEM_EMPRESAS)).toBeInTheDocument();
    expect(getEmpresas).not.toHaveBeenCalled();
  });
});
