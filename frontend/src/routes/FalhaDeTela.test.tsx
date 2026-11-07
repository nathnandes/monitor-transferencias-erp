import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ehFalhaDeCarga, FalhaDeTela } from "./FalhaDeTela";

function Explode({ erro }: { erro: Error }): never {
  throw erro;
}

afterEach(() => vi.restoreAllMocks());

describe("ehFalhaDeCarga", () => {
  it("reconhece as mensagens de import dinâmico dos navegadores", () => {
    expect(ehFalhaDeCarga(new TypeError("Failed to fetch dynamically imported module: /assets/x.js"))).toBe(true);
    expect(ehFalhaDeCarga(new TypeError("Importing a module script failed."))).toBe(true);
    expect(ehFalhaDeCarga(new TypeError("error loading dynamically imported module"))).toBe(true);
    expect(ehFalhaDeCarga(new Error("x is undefined"))).toBe(false);
    expect(ehFalhaDeCarga("texto")).toBe(false);
  });
});

describe("FalhaDeTela", () => {
  it("mostra a tela de recarregar em vez de deixar a página em branco", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <FalhaDeTela chave="/dashboard">
        <Explode erro={new TypeError("Failed to fetch dynamically imported module")} />
      </FalhaDeTela>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível abrir esta tela");
    expect(screen.getByRole("button", { name: "Recarregar página" })).toBeInTheDocument();
  });

  it("diferencia erro de renderização de falha de carga", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <FalhaDeTela chave="/dashboard">
        <Explode erro={new Error("bug")} />
      </FalhaDeTela>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Algo deu errado nesta tela");
  });

  it("esquece a falha ao navegar para outra rota", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(
      <FalhaDeTela chave="/dashboard">
        <Explode erro={new Error("bug")} />
      </FalhaDeTela>,
    );
    rerender(
      <FalhaDeTela chave="/transferencias">
        <p>tela nova</p>
      </FalhaDeTela>,
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("tela nova")).toBeInTheDocument();
  });
});
