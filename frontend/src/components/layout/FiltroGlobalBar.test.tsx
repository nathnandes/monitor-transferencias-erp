import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { empresa } from "../../test/factories";
import type { EmpresaResumo } from "../../types/api";
import { FiltroGlobalBar } from "./FiltroGlobalBar";

function Barra({ empresas = [empresa("01"), empresa("03")] }: { empresas?: EmpresaResumo[] | null }) {
  const estado = useFiltroGlobal();
  return <FiltroGlobalBar estado={estado} empresas={empresas} />;
}

const botao = (nome: string) => screen.getByRole("button", { name: nome });

beforeEach(() => window.history.replaceState(null, "", "/"));

describe("FiltroGlobalBar", () => {
  it("começa em consolidado + hoje e mostra com o que compara", () => {
    render(<Barra />);
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(botao("Hoje")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/^Comparando com (segunda|terça|quarta|quinta|sexta) passada|^Comparando com (sábado|domingo) passado/)).toBeInTheDocument();
  });

  it("grava empresa e período na URL, preserva o resto e volta a tabela para a página 1", async () => {
    window.history.replaceState(null, "", "/?status=ERRO&pagina=3");
    render(<Barra />);

    await userEvent.click(botao("Mês"));
    expect(window.location.search).toBe("?status=ERRO&periodo=mes");
    expect(botao("Mês")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Comparando com mesmo período de/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox"), "03");
    expect(window.location.search).toBe("?status=ERRO&empresa=03&periodo=mes");


    window.history.back();
    await screen.findByDisplayValue("Consolidado (todas)");
  });

  it("Tudo não compara", async () => {
    render(<Barra />);
    await userEvent.click(botao("Tudo"));
    expect(window.location.search).toBe("?periodo=tudo");
    expect(screen.queryByText(/Comparando com/)).not.toBeInTheDocument();
  });

  it("personalizado: só aplica intervalo válido", async () => {
    render(<Barra />);
    await userEvent.click(botao("Personalizado"));
    expect(window.location.search).toBe("");

    await userEvent.type(screen.getByLabelText("De"), "2026-09-20");
    await userEvent.type(screen.getByLabelText("Até"), "2026-09-10");
    expect(screen.getByRole("alert")).toHaveTextContent("A data inicial não pode ser posterior à data final.");
    expect(botao("Aplicar")).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Até"));
    await userEvent.type(screen.getByLabelText("Até"), "2026-09-26");
    await userEvent.click(botao("Aplicar"));
    expect(window.location.search).toBe("?periodo=personalizado&data_inicial=2026-09-20&data_final=2026-09-26");
    expect(screen.getByText("Comparando com 7 dias anteriores (13/09 a 19/09)")).toBeInTheDocument();
  });

  it("empresa do link aparece mesmo sem a lista (usuário sem o módulo Dashboard)", () => {
    window.history.replaceState(null, "", "/?empresa=05");
    render(<Barra empresas={null} />);
    expect(screen.getByRole("combobox")).toHaveValue("05");
    expect(screen.getByRole("option", { name: "Empresa 05" })).toBeInTheDocument();
  });
});
