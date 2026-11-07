import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/apiClient";
import { getAlertas, getResumoAlertas } from "../../services/alertasService";
import { empresa } from "../../test/factories";
import { authFalso, renderComSessao } from "../../test/sessao";
import type { Alerta, PaginaAlertas } from "../../types/api";
import { AlertasPage, TITULO_ALERTAS } from "./AlertasPage";

vi.mock("../../services/alertasService", () => ({ getAlertas: vi.fn(), getResumoAlertas: vi.fn() }));

function alerta(parcial: Partial<Alerta> = {}): Alerta {
  return {
    id: 1,
    regra: "transferencia_atrasada",
    severidade: "CRITICAL",
    status: "ABERTO",
    titulo: "Transferência DEMO-TRF-0007 pendente há 26h",
    mensagem: "Origem: 01 - Empresa 01\nDestino: 02 - Empresa 02",
    empresa: empresa("01"),
    transferencia: { id: 7, id_erp: "DEMO-TRF-0007" },
    aberto_em: "2026-10-01T12:00:00Z",
    visto_em: "2026-10-02T12:00:00Z",
    resolvido_em: null,
    ...parcial,
  };
}

function paginaDe(itens: Alerta[], parcial: Partial<PaginaAlertas> = {}): PaginaAlertas {
  return { total: itens.length, pagina: 1, tamanho_pagina: 20, total_paginas: itens.length ? 1 : 0, itens, ...parcial };
}

const ultimaChamada = () => vi.mocked(getAlertas).mock.calls.at(-1)!;
const auth = () => authFalso(["ALERTAS"]);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getResumoAlertas).mockResolvedValue({
    abertos: 3,
    por_severidade: { INFO: 0, WARNING: 1, ERROR: 0, CRITICAL: 2 },
  });
  vi.mocked(getAlertas).mockResolvedValue(paginaDe([alerta()]));
});

describe("AlertasPage", () => {
  it("mostra o resumo por severidade e os alertas abertos por padrão", async () => {
    renderComSessao(<AlertasPage />, { auth: auth() });

    expect(screen.getByRole("heading", { level: 1, name: TITULO_ALERTAS })).toBeInTheDocument();
    expect(await screen.findByText("Transferência DEMO-TRF-0007 pendente há 26h")).toBeInTheDocument();
    expect(screen.getByText(/Destino: 02 - Empresa 02/)).toBeInTheDocument();
    expect(ultimaChamada()[0]).toEqual({ status: "ABERTO" });

    const resumo = screen.getByRole("region", { name: "Alertas abertos por severidade" });
    await waitFor(() => expect(resumo).toHaveTextContent("3"));
    expect(resumo).toHaveTextContent("Crítico");
  });

  it("filtra por situação e severidade e volta para a página 1", async () => {
    vi.mocked(getAlertas).mockResolvedValue(paginaDe([alerta()], { total: 45, total_paginas: 3 }));
    renderComSessao(<AlertasPage />, { auth: auth() });
    await screen.findByText("Transferência DEMO-TRF-0007 pendente há 26h");

    await userEvent.click(screen.getByRole("button", { name: "Próxima" }));
    await waitFor(() => expect(ultimaChamada()[1]).toBe(2));

    await userEvent.selectOptions(screen.getByLabelText("Severidade"), "CRITICAL");
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ status: "ABERTO", severidade: "CRITICAL" }));
    expect(ultimaChamada()[1]).toBe(1);

    await userEvent.selectOptions(screen.getByLabelText("Situação"), "");
    await waitFor(() => expect(ultimaChamada()[0]).toEqual({ severidade: "CRITICAL" }));
  });

  it("alerta resolvido mostra o selo e a hora da resolução", async () => {
    vi.mocked(getAlertas).mockResolvedValue(
      paginaDe([alerta({ status: "RESOLVIDO", resolvido_em: "2026-10-02T13:00:00Z" })]),
    );
    renderComSessao(<AlertasPage />, { auth: auth() });

    expect(await screen.findByText("Resolvido")).toBeInTheDocument();
    expect(screen.getByText(/Resolvido 02\/10\/2026/)).toBeInTheDocument();
  });

  it("sem alertas abertos mostra estado tranquilo", async () => {
    vi.mocked(getAlertas).mockResolvedValue(paginaDe([]));
    renderComSessao(<AlertasPage />, { auth: auth() });

    expect(await screen.findByText("Nenhum alerta aberto.")).toBeInTheDocument();
  });

  it("erro da API mostra a falha com opção de tentar de novo", async () => {
    vi.mocked(getAlertas).mockRejectedValue(new ApiError("Falha", "http", 500));
    renderComSessao(<AlertasPage />, { auth: auth() });

    expect(await screen.findByText("Falha ao carregar os alertas")).toBeInTheDocument();
    vi.mocked(getAlertas).mockResolvedValue(paginaDe([alerta()]));
    await userEvent.click(screen.getByRole("button", { name: /Tentar novamente/ }));
    expect(await screen.findByText("Transferência DEMO-TRF-0007 pendente há 26h")).toBeInTheDocument();
  });
});
