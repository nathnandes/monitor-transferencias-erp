import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { NivelStatusEmpresa, StatusEmpresa } from "../../../types/api";
import { CompanyStatusList, ordenarPorGravidade } from "./CompanyStatusList";

function linha(codigo: string, status: NivelStatusEmpresa, pendentes = 0, criticas = 0): StatusEmpresa {
  return {
    empresa: { id: Number(codigo), codigo, nome: `Loja ${codigo}` },
    status,
    motivos: status === "ok" ? [] : [`Motivo ${codigo}`],
    ultima_sincronizacao: null,
    pendentes,
    pendentes_atrasadas: criticas,
    pendentes_criticas: criticas,
    com_erro: 0,
  } as StatusEmpresa;
}

describe("CompanyStatusList", () => {
  it("ordena: crítico, atenção, ok; no mesmo nível, mais pendência crítica primeiro", () => {
    const ordem = ordenarPorGravidade([
      linha("01", "ok"),
      linha("02", "atencao"),
      linha("03", "critico", 5, 1),
      linha("04", "critico", 5, 4),
    ]).map((s) => s.empresa.codigo);
    expect(ordem).toEqual(["04", "03", "02", "01"]);
  });

  it("empresas em dia viram uma linha compacta e o resumo filtra por situação", () => {
    render(
      <MemoryRouter>
        <CompanyStatusList itens={[linha("01", "ok"), linha("02", "ok"), linha("03", "critico", 3, 2)]} />
      </MemoryRouter>,
    );
    expect(screen.getByText("2 empresas em dia")).toBeInTheDocument();
    expect(screen.getByText("Motivo 03")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver transferências/ })).toHaveAttribute(
      "href",
      "/transferencias?empresa=03&periodo=tudo",
    );

    fireEvent.click(screen.getByRole("button", { name: /Crítico/ }));
    expect(screen.queryByText("2 empresas em dia")).not.toBeInTheDocument();
    expect(screen.getByText("Motivo 03")).toBeInTheDocument();
  });
});
