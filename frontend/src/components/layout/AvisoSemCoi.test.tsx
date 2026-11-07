import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../features/auth/AuthContext";
import { getTransferenciasSemCoi } from "../../services/coiService";
import { pagina, transferencia, transferenciaCoiErrado } from "../../test/factories";
import { authFalso } from "../../test/sessao";
import type { Modulo } from "../../types/auth";
import { AvisoSemCoi, INTERVALO_AVISO_COI_MS, ROTA_SEM_COI } from "./AvisoSemCoi";

vi.mock("../../services/coiService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../services/coiService")>()),
  getTransferenciasSemCoi: vi.fn(),
}));

function renderAviso(modulos: Modulo[] = ["TRANSFERENCIAS"], variante?: "padrao" | "tv") {
  return render(
    <AuthContext.Provider value={authFalso(modulos)}>
      <MemoryRouter>
        <AvisoSemCoi variante={variante} />
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("AvisoSemCoi", () => {
  beforeEach(() => vi.mocked(getTransferenciasSemCoi).mockReset());
  afterEach(() => vi.useRealTimers());

  it("com transferência com COI errado: faixa de alerta com total, motivo e links", async () => {
    vi.mocked(getTransferenciasSemCoi).mockResolvedValue(pagina([transferenciaCoiErrado()], { total: 7 }));
    renderAviso();

    const alerta = await screen.findByRole("alert", { name: "Transferências com COI errado" });
    expect(alerta).toHaveTextContent("7 transferências com COI errado");
    expect(alerta).toHaveTextContent(/foram feitas erradas no ERP/);
    expect(alerta).toHaveTextContent("e mais 6");
    expect(screen.getByRole("link", { name: "DEMO-TRF-0004 · 01 → 02" })).toHaveAttribute(
      "href",
      `${ROTA_SEM_COI}&detalhe=4`,
    );
    expect(screen.getByRole("link", { name: /Ver transferências/ })).toHaveAttribute("href", ROTA_SEM_COI);
  });

  it("sem pendência de COI: não mostra nada", async () => {
    vi.mocked(getTransferenciasSemCoi).mockResolvedValue(pagina([]));
    renderAviso();
    await vi.waitFor(() => expect(getTransferenciasSemCoi).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sem o módulo TRANSFERENCIAS: nem consulta", () => {
    renderAviso(["DASHBOARD"]);
    expect(getTransferenciasSemCoi).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("modo TV: mesma faixa, sem links", async () => {
    vi.mocked(getTransferenciasSemCoi).mockResolvedValue(pagina([transferenciaCoiErrado()]));
    renderAviso(["TRANSFERENCIAS"], "tv");
    expect(await screen.findByRole("alert")).toHaveTextContent("1 transferência com COI errado");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("confere de novo sozinho e some quando o COI é corrigido", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getTransferenciasSemCoi)
      .mockResolvedValueOnce(pagina([transferenciaCoiErrado()]))
      .mockResolvedValue(pagina([transferencia({ situacao_coi: "CORRETO" })], { total: 0 }));
    renderAviso();
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(INTERVALO_AVISO_COI_MS);
    });

    expect(getTransferenciasSemCoi).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
