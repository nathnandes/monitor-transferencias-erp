import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "./layout/AppShell";
import { EnvironmentBadge, TEXTO_SIMULADO } from "./layout/EnvironmentBadge";
import { Header } from "./layout/Header";
import { EmptyState } from "./ui/EmptyState";
import { ErrorState } from "./ui/ErrorState";
import { LoadingState } from "./ui/LoadingState";
import { MetricCard } from "./ui/MetricCard";
import { Panel } from "./ui/Panel";
import { StatusBadge } from "./ui/StatusBadge";

describe("AppShell + Header", () => {
  it("renderiza título, selo, botão Atualizar e conteúdo", async () => {
    const atualizar = vi.fn();
    render(
      <AppShell header={<Header titulo="Dashboard de Operações ERP" selo={<span>selo</span>} aoAtualizar={atualizar} />}>
        <p>conteúdo</p>
      </AppShell>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard de Operações ERP" })).toBeInTheDocument();
    expect(screen.getByText("selo")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveTextContent("conteúdo");
    expect(screen.getByRole("link", { name: "Pular para o conteúdo" })).toHaveAttribute("href", "#conteudo");

    await userEvent.click(screen.getByRole("button", { name: "Atualizar" }));
    expect(atualizar).toHaveBeenCalledOnce();
  });

  it("omite Atualizar quando não há ação", () => {
    render(<Header titulo="T" selo={null} />);
    expect(screen.queryByRole("button", { name: "Atualizar" })).not.toBeInTheDocument();
  });
});

describe("EnvironmentBadge", () => {
  it("mostra o aviso de dados simulados", () => {
    render(<EnvironmentBadge health={{ status: "ok", app: "x", env: "development" }} simulado />);
    expect(screen.getByText(TEXTO_SIMULADO)).toHaveTextContent("Ambiente de desenvolvimento — dados simulados");
  });

  it("mostra o ambiente quando os dados não são simulados", () => {
    render(<EnvironmentBadge health={{ status: "ok", app: "x", env: "producao" }} simulado={false} />);
    expect(screen.getByText("Ambiente: Produção")).toBeInTheDocument();
  });
});

describe("MetricCard", () => {
  it("mostra '—' e 'Carregando...' enquanto carrega, nunca um número", () => {
    render(<MetricCard rotulo="Pendentes" valor="5" carregando />);
    const card = screen.getByText("Pendentes").closest("article")!;
    expect(within(card).getByText("—")).toBeInTheDocument();
    expect(within(card).getByText("Carregando...")).toBeInTheDocument();
    expect(within(card).queryByText("5")).not.toBeInTheDocument();
    expect(card).toHaveAttribute("aria-busy", "true");
  });

  it("mostra '—' sem valor e o valor quando existe", () => {
    const { rerender } = render(<MetricCard rotulo="Erros" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    rerender(<MetricCard rotulo="Erros" valor="7" detalhe="14% do total" />);
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("14% do total")).toBeInTheDocument();
  });
});

describe("estados e superfícies", () => {
  it("StatusBadge mostra o texto", () => {
    render(<StatusBadge tom="critico">Crítico</StatusBadge>);
    expect(screen.getByText("Crítico")).toBeInTheDocument();
  });

  it("Panel mostra título e subtítulo", () => {
    render(<Panel titulo="Gráficos" subtitulo="sub">corpo</Panel>);
    expect(screen.getByRole("heading", { name: "Gráficos" })).toBeInTheDocument();
    expect(screen.getByText("sub")).toBeInTheDocument();
  });

  it("LoadingState e EmptyState", () => {
    render(
      <>
        <LoadingState />
        <EmptyState titulo="Nada aqui" descricao="Sem registros" />
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Carregando...");
    expect(screen.getByText("Nada aqui")).toBeInTheDocument();
  });

  it("ErrorState oferece tentar novamente", async () => {
    const tentar = vi.fn();
    render(<ErrorState mensagem="API fora" aoTentarNovamente={tentar} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API fora");
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(tentar).toHaveBeenCalledOnce();
  });
});
