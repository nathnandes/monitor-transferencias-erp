import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { resumo } from "../../../test/factories";
import { MetricsGrid } from "./MetricsGrid";

const semAcao = () => {};
const card = (rotulo: string) => screen.getByText(rotulo).closest("article")!;

describe("MetricsGrid", () => {
  it("exibe os totais do resumo", () => {
    render(<MetricsGrid resumo={resumo()} carregando={false} erro={null} aoTentarNovamente={semAcao} />);
    expect(within(card("Transferências criadas")).getByText("36")).toBeInTheDocument();
    expect(within(card("Processadas")).getByText("26")).toBeInTheDocument();
    expect(within(card("Com erro agora")).getByText("5")).toBeInTheDocument();
    expect(within(card("Empresas ativas")).getByText("6")).toBeInTheDocument();
    expect(within(card("Última sincronização")).getByText("há 2 h")).toBeInTheDocument();
    expect(within(card("Última sincronização")).getByText("Parcial")).toBeInTheDocument();
  });

  it("mostra placeholders enquanto carrega", () => {
    render(<MetricsGrid resumo={null} carregando erro={null} aoTentarNovamente={semAcao} />);
    expect(screen.getAllByText("Carregando...")).toHaveLength(6);
    expect(screen.getAllByText("—")).toHaveLength(6);
  });

  it("compara o fluxo do período e deixa a situação de agora sem seta", () => {
    const dados = resumo({
      periodo: { criadas: 12, processadas: 8, eventos: 3 },
      comparacao: { criadas: 10, processadas: 10, eventos: 3 },
    });
    render(
      <MetricsGrid
        resumo={dados}
        carregando={false}
        erro={null}
        aoTentarNovamente={semAcao}
        rotuloComparacao="sexta passada"
        escopo="Hoje · consolidado"
      />,
    );
    const criadas = card("Transferências criadas");
    expect(within(criadas).getByText("▲ 20%")).toBeInTheDocument();
    expect(within(criadas).getByText("20% a mais que sexta passada (10).")).toBeInTheDocument();
    expect(within(criadas).getByText("Hoje · consolidado")).toBeInTheDocument();

    const processadas = card("Processadas");
    expect(within(processadas).getByText("8")).toBeInTheDocument();
    expect(within(processadas).getByText("▼ 20%")).toHaveClass("text-critico-texto");

    expect(within(card("Pendentes agora")).queryByText(/vs\./)).not.toBeInTheDocument();
    expect(within(card("Pendentes agora")).getByText("4 há mais de 24h · de qualquer data")).toBeInTheDocument();
  });
});
