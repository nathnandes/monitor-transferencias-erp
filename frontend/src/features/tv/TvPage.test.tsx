import { act, cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getResumoDashboard } from "../../services/dashboardService";
import { empresa, resumo } from "../../test/factories";
import { renderComSessao } from "../../test/sessao";
import type { StatusEmpresa } from "../../types/api";
import { INTERVALO_TV_MS, TvPage } from "./TvPage";

vi.mock("../../services/dashboardService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/dashboardService")>()),
  getResumoDashboard: vi.fn(),
}));

const linha = (codigo: string, status: StatusEmpresa["status"]): StatusEmpresa => ({
  empresa: empresa(codigo),
  status,
  motivos: [],
  ultima_sincronizacao: null,
  pendentes: 0,
  pendentes_atrasadas: 0,
  pendentes_criticas: 0,
  com_erro: 0,
});

const indicador = (rotulo: string) => screen.getByRole("heading", { name: rotulo }).closest("article")!;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  window.history.replaceState(null, "", "/tv?empresa=03&periodo=mes");
  vi.mocked(getResumoDashboard).mockResolvedValue(
    resumo({
      periodo: { criadas: 30, processadas: 25, eventos: 4 },
      comparacao: { criadas: 20, processadas: 25, eventos: 4 },
      status_por_empresa: [linha("02", "critico"), linha("03", "ok"), linha("06", "critico")],
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("TvPage", () => {
  it("mostra os 5 indicadores no filtro da URL, com comparação", async () => {
    renderComSessao(<TvPage />, { rota: "/tv" });
    expect(await within(indicador("Transferências criadas")).findByText("36")).toBeInTheDocument();
    expect(within(indicador("Transferências criadas")).getByText("▲ 50%")).toBeInTheDocument();
    expect(within(indicador("Processadas")).getByText("25")).toBeInTheDocument();
    expect(within(indicador("Pendentes agora")).getByText("5")).toBeInTheDocument();
    expect(within(indicador("Com erro agora")).getByText("5")).toBeInTheDocument();
    expect(within(indicador("Empresas em situação crítica")).getByText("Lojas 02 · 06")).toBeInTheDocument();

    const [params] = vi.mocked(getResumoDashboard).mock.calls[0]!;
    expect(params).toMatchObject({ empresa: "03" });
    expect(params?.data_inicial).toMatch(/-01$/);
    expect(screen.getByText(/· Empresa 03$/)).toBeInTheDocument();
  });

  it("atualiza sozinho a cada minuto e pausa com a aba escondida", async () => {
    renderComSessao(<TvPage />, { rota: "/tv" });
    await within(indicador("Transferências criadas")).findByText("36");
    expect(getResumoDashboard).toHaveBeenCalledTimes(1);

    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_TV_MS));
    expect(getResumoDashboard).toHaveBeenCalledTimes(2);

    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_TV_MS * 3));
    expect(getResumoDashboard).toHaveBeenCalledTimes(2);


    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    document.dispatchEvent(new Event("visibilitychange"));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(getResumoDashboard).toHaveBeenCalledTimes(3);
  });

  it("sem conexão: mantém os números e avisa", async () => {
    renderComSessao(<TvPage />, { rota: "/tv" });
    await within(indicador("Transferências criadas")).findByText("36");

    vi.mocked(getResumoDashboard).mockRejectedValue(new Error("rede"));
    await act(() => vi.advanceTimersByTimeAsync(INTERVALO_TV_MS));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sem conexão com o servidor");
    expect(within(indicador("Transferências criadas")).getByText("36")).toBeInTheDocument();
  });
});
