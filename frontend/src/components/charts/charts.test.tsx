import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChartPanel } from "./ChartPanel";
import { COR_SERIE_1, COR_SERIE_2, corDaSeveridade, corDoStatus } from "./chartTheme";
import { CompanyChart } from "./CompanyChart";
import { SeverityChart } from "./SeverityChart";
import { StatusChart } from "./StatusChart";
import { GranularidadeToggle, TrendChart } from "./TrendChart";

const semAcao = () => {};


async function abrirTabela() {
  await userEvent.click(screen.getByText("Ver dados em tabela"));
  return screen.getByRole("table");
}

describe("cores padronizadas", () => {
  it("status e severidade seguem a convenção", () => {
    expect(corDoStatus("PROCESSADA")).toBe("#16a34a");
    expect(corDoStatus("PENDENTE")).toBe("#f39c12");
    expect(corDoStatus("ERRO")).toBe("#dc2626");
    expect(corDoStatus("OUTROS")).toBe("#898781");
    expect(corDaSeveridade("INFO")).toBe("#2563eb");
    expect(corDaSeveridade("WARNING")).toBe("#f39c12");
    expect(corDaSeveridade("CRITICAL")).toBe("#dc2626");
  });
});

describe("StatusChart", () => {
  it("desenha uma barra por status, com cor e rótulo, e a tabela com %", async () => {
    const { container } = render(
      <StatusChart
        dados={[
          { status: "PROCESSADA", total: 26 },
          { status: "PENDENTE", total: 5 },
          { status: "ERRO", total: 5 },
        ]}
      />,
    );
    const barras = container.querySelectorAll(".recharts-bar-rectangle path");
    expect([...barras].map((b) => b.getAttribute("fill"))).toEqual(["#16a34a", "#f39c12", "#dc2626"]);
    const grafico = container.querySelector<HTMLElement>(".recharts-wrapper")!;
    expect(within(grafico).getByText("PROCESSADA")).toBeInTheDocument();

    const tabela = await abrirTabela();
    const linha = within(tabela).getByText("PROCESSADA").closest("tr")!;
    expect(linha).toHaveTextContent("26");
    expect(linha).toHaveTextContent("72%");
  });
});

describe("SeverityChart", () => {
  it("usa a cor de cada severidade e lista os totais", async () => {
    const { container } = render(
      <SeverityChart
        dados={[
          { severidade: "INFO", total: 4 },
          { severidade: "WARNING", total: 7 },
          { severidade: "ERROR", total: 7 },
          { severidade: "CRITICAL", total: 3 },
        ]}
      />,
    );
    const barras = container.querySelectorAll(".recharts-bar-rectangle path");
    expect([...barras].map((b) => b.getAttribute("fill"))).toEqual(["#2563eb", "#f39c12", "#ec835a", "#dc2626"]);
    const tabela = await abrirTabela();
    expect(within(tabela).getByText("CRITICAL").closest("tr")).toHaveTextContent("3");
  });
});

describe("CompanyChart", () => {
  it("mostra legenda das duas séries e a tabela com o nome da empresa", async () => {
    const { container } = render(
      <CompanyChart
        dados={[
          { codigo: "01", nome: "Empresa 01", saidas: 6, entradas: 4 },
          { codigo: "02", nome: "Empresa 02", saidas: 1, entradas: 3 },
        ]}
      />,
    );
    const legenda = container.querySelector<HTMLElement>(".recharts-legend-wrapper")!;
    expect(within(legenda).getByText("Saídas (origem)")).toBeInTheDocument();
    expect(within(legenda).getByText("Entradas (destino)")).toBeInTheDocument();
    const fills = new Set([...container.querySelectorAll(".recharts-bar-rectangle path")].map((b) => b.getAttribute("fill")));
    expect(fills).toEqual(new Set([COR_SERIE_1, COR_SERIE_2]));

    const tabela = await abrirTabela();
    expect(within(tabela).getByText("01 — Empresa 01").closest("tr")).toHaveTextContent(/6\s*4/);
  });
});

describe("TrendChart", () => {
  it("desenha a área e lista os períodos na tabela", async () => {
    const { container } = render(
      <TrendChart
        dados={[
          { chave: "2026-09-20", rotulo: "20/09", rotuloCompleto: "20/09/2026", total: 2 },
          { chave: "2026-09-21", rotulo: "21/09", rotuloCompleto: "21/09/2026", total: 0 },
        ]}
      />,
    );
    expect(container.querySelector(".recharts-area-curve")).toHaveAttribute("stroke", COR_SERIE_1);
    const tabela = await abrirTabela();
    expect(within(tabela).getByText("20/09/2026").closest("tr")).toHaveTextContent("2");
  });

  it("alterna dia/semana com aria-pressed", async () => {
    const mudar = vi.fn();
    render(<GranularidadeToggle valor="dia" aoMudar={mudar} />);
    expect(screen.getByRole("button", { name: "Dia" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Semana" })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: "Semana" }));
    expect(mudar).toHaveBeenCalledWith("semana");
  });
});

describe("ChartPanel", () => {
  const base = { titulo: "Por status", aoTentarNovamente: semAcao };

  it("carregando", () => {
    render(<ChartPanel {...base} carregando erro={null} vazio={false}><p>gráfico</p></ChartPanel>);
    expect(screen.getByRole("status")).toHaveTextContent("Carregando...");
    expect(screen.queryByText("gráfico")).not.toBeInTheDocument();
  });

  it("erro isolado no painel, com tentar novamente", async () => {
    const tentar = vi.fn();
    render(
      <ChartPanel {...base} carregando={false} erro={new Error("HTTP 500")} vazio={false} aoTentarNovamente={tentar}>
        <p>gráfico</p>
      </ChartPanel>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Falha ao carregar: Por status");
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(tentar).toHaveBeenCalledOnce();
  });

  it("vazio", () => {
    render(<ChartPanel {...base} carregando={false} erro={null} vazio mensagemVazio="Nada aqui."><p>gráfico</p></ChartPanel>);
    expect(screen.getByText("Sem dados para exibir")).toBeInTheDocument();
    expect(screen.getByText("Nada aqui.")).toBeInTheDocument();
  });

  it("sucesso: figura com descrição para leitor de tela", () => {
    render(
      <ChartPanel {...base} carregando={false} erro={null} vazio={false} descricao="PROCESSADA: 26">
        <p>gráfico</p>
      </ChartPanel>,
    );
    expect(screen.getByRole("figure", { name: "Por status" })).toHaveTextContent("PROCESSADA: 26");
    expect(screen.getByText("gráfico")).toBeInTheDocument();
  });
});
