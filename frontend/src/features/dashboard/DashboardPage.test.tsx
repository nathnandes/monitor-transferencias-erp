import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/apiClient";
import { getHealthLive, getResumoDashboard } from "../../services/dashboardService";
import { getEmpresas } from "../../services/empresasService";
import { getIndicadoresEmpresas } from "../../services/indicadoresService";
import { coletarTransferencias, getTransferencias } from "../../services/transferenciasService";
import { indicadores, resumo } from "../../test/factories";
import { renderComSessao } from "../../test/sessao";
import type { Empresa, ResumoDashboard } from "../../types/api";
import { DashboardPage } from "./DashboardPage";


vi.mock("../../services/dashboardService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/dashboardService")>()),
  getResumoDashboard: vi.fn(),
  getHealthLive: vi.fn(),
}));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));
vi.mock("../../services/indicadoresService", () => ({ getIndicadoresEmpresas: vi.fn() }));
vi.mock("../../services/transferenciasService", () => ({
  getTransferencias: vi.fn(),
  coletarTransferencias: vi.fn(),
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


function adiado<T>() {
  let resolver!: (v: T) => void;
  let rejeitar!: (e: unknown) => void;
  const promessa = new Promise<T>((res, rej) => {
    resolver = res;
    rejeitar = rej;
  });
  return { promessa, resolver, rejeitar };
}

const card = (rotulo: string) => screen.getByText(rotulo).closest("article")!;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getHealthLive).mockResolvedValue({ status: "ok", app: "erp-automation", env: "development" });
  vi.mocked(getEmpresas).mockResolvedValue([empresaDemo]);
  vi.mocked(getResumoDashboard).mockReset();


  vi.mocked(getIndicadoresEmpresas).mockResolvedValue(indicadores({ empresas: [] }));
});

describe("DashboardPage — resumo operacional", () => {
  it("mostra carregando e depois os valores reais do resumo", async () => {
    const pendente = adiado<ResumoDashboard>();
    vi.mocked(getResumoDashboard).mockReturnValue(pendente.promessa);
    renderComSessao(<DashboardPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Dashboard de Operações ERP" })).toBeInTheDocument();
    expect(within(card("Processadas")).getByText("Carregando...")).toBeInTheDocument();
    expect(within(card("Processadas")).getByText("—")).toBeInTheDocument();

    pendente.resolver(resumo());
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument());
    expect(within(card("Processadas")).getByText("26")).toBeInTheDocument();
    expect(within(card("Pendentes agora")).getByText("5")).toBeInTheDocument();
    expect(within(card("Com erro agora")).getByText("5")).toBeInTheDocument();
    expect(within(card("Empresas ativas")).getByText("6")).toBeInTheDocument();
    expect(within(card("Última sincronização")).getByText("há 2 h")).toBeInTheDocument();
    expect(within(card("Última sincronização")).getByText("Parcial")).toBeInTheDocument();
    expect(within(card("Última sincronização")).getByText("26/09/2026, 06:00")).toBeInTheDocument();

    expect(screen.getByText(/^Atualizado às \d{2}:\d{2}:\d{2}$/)).toBeInTheDocument();
    expect(screen.getByText("Ambiente de desenvolvimento — dados simulados")).toBeInTheDocument();
  });

  it("mostra erro de rede claro e se recupera com Tentar novamente", async () => {
    vi.mocked(getResumoDashboard)
      .mockRejectedValueOnce(new ApiError("Não foi possível conectar à API.", "rede"))
      .mockResolvedValueOnce(resumo());
    renderComSessao(<DashboardPage />);


    const titulo = await screen.findByText("Não foi possível carregar o resumo");
    const alerta = titulo.closest<HTMLElement>("[role=alert]")!;
    expect(alerta).toHaveTextContent("Não foi possível conectar à API.");

    await userEvent.click(within(alerta).getByRole("button", { name: "Tentar novamente" }));
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument());
    expect(getResumoDashboard).toHaveBeenCalledTimes(2);
  });

  it("mostra estado vazio quando o banco não tem dados", async () => {
    vi.mocked(getResumoDashboard).mockResolvedValue(
      resumo({
        transferencias: { total: 0, processadas: 0, pendentes: 0, com_erro: 0 },
        empresas_ativas: 0,
        ultima_sincronizacao: null,
        status_por_empresa: [],
      }),
    );
    renderComSessao(<DashboardPage />);
    expect(await screen.findByText("Nenhum dado operacional no banco")).toBeInTheDocument();
    expect(screen.queryByText("Transferências criadas")).not.toBeInTheDocument();
  });

  it("Atualizar busca o resumo de novo e mostra os novos valores", async () => {
    vi.mocked(getResumoDashboard)
      .mockResolvedValueOnce(resumo())
      .mockResolvedValueOnce(resumo({ transferencias: { total: 40, processadas: 30, pendentes: 5, com_erro: 5 } }));
    renderComSessao(<DashboardPage />);
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument());

    await userEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("40")).toBeInTheDocument());
    expect(getResumoDashboard).toHaveBeenCalledTimes(2);
  });

  it("mantém os últimos dados e avisa quando a atualização falha", async () => {
    vi.mocked(getResumoDashboard)
      .mockResolvedValueOnce(resumo())
      .mockRejectedValueOnce(new ApiError("A API respondeu com erro HTTP 500.", "http", 500));
    renderComSessao(<DashboardPage />);
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument());

    await userEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
    const alerta = await screen.findByText(/Falha ao atualizar/);
    expect(alerta.closest("[role=alert]")).toHaveTextContent("HTTP 500");
    expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument();
  });

  it("não consulta transferências: a listagem é do módulo TRANSFERENCIAS", async () => {
    vi.mocked(getResumoDashboard).mockResolvedValue(resumo());
    renderComSessao(<DashboardPage />);
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument());
    expect(screen.getByRole("figure", { name: "Transferências por status" })).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Eventos por severidade" })).toBeInTheDocument();
    expect(getTransferencias).not.toHaveBeenCalled();
    expect(coletarTransferencias).not.toHaveBeenCalled();
  });
});

describe("DashboardPage — indicadores por empresa", () => {
  it("pede a série no mesmo filtro e mostra um bloco por empresa", async () => {
    vi.mocked(getResumoDashboard).mockResolvedValue(resumo());
    vi.mocked(getIndicadoresEmpresas).mockResolvedValue(indicadores());
    window.history.replaceState(null, "", "/?empresa=01&periodo=personalizado&data_inicial=2026-09-28&data_final=2026-09-30");
    renderComSessao(<DashboardPage />);

    const bloco = await screen.findByRole("region", { name: /Empresa 01/ });
    expect(getIndicadoresEmpresas).toHaveBeenCalledWith(
      { empresa: "01", data_inicial: "2026-09-28", data_final: "2026-09-30" },
      expect.any(AbortSignal),
    );
    expect(within(bloco).getByRole("heading", { name: /Enviadas/ }).closest("article")).toHaveTextContent("6");
    expect(screen.getByText(/uma coluna por dia/)).toBeInTheDocument();
    window.history.replaceState(null, "", "/");
  });

  it("com várias empresas, mostra uma por vez e troca pelo seletor", async () => {
    vi.mocked(getResumoDashboard).mockResolvedValue(resumo());
    const base = indicadores();
    const outra = { ...base.empresas[0]!, empresa: { id: 2, codigo: "02", nome: "Empresa 02" } };
    vi.mocked(getIndicadoresEmpresas).mockResolvedValue({ ...base, empresas: [base.empresas[0]!, outra] });
    renderComSessao(<DashboardPage />);

    expect(await screen.findByRole("region", { name: /Empresa 01/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Empresa 02/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /02\s*Empresa 02/ }));
    expect(screen.getByRole("region", { name: /Empresa 02/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /Empresa 01/ })).not.toBeInTheDocument();
  });

  it("falha nos indicadores não derruba o resto do dashboard", async () => {
    vi.mocked(getResumoDashboard).mockResolvedValue(resumo());
    vi.mocked(getIndicadoresEmpresas).mockRejectedValue(new ApiError("Servidor fora", "http", 500));
    renderComSessao(<DashboardPage />);

    expect(await screen.findByText("Não foi possível carregar os indicadores por empresa")).toBeInTheDocument();
    await waitFor(() => expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument());
  });
});
