import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { CampoSenha } from "./CampoSenha";

function Formulario({ disabled = false }: { disabled?: boolean }) {
  const [senha, setSenha] = useState("");
  return (
    <>
      <label htmlFor="s">Senha</label>
      <CampoSenha id="s" value={senha} onChange={(e) => setSenha(e.target.value)} disabled={disabled} />
    </>
  );
}

describe("CampoSenha", () => {
  it("começa oculto e alterna entre mostrar e ocultar sem perder o valor nem o foco", async () => {
    render(<Formulario />);
    const campo = screen.getByLabelText("Senha");
    expect(campo).toHaveAttribute("type", "password");

    await userEvent.type(campo, "Segredo@123");
    await userEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(campo).toHaveAttribute("type", "text");
    expect(campo).toHaveValue("Segredo@123");
    expect(campo).toHaveFocus();

    const ocultar = screen.getByRole("button", { name: "Ocultar senha" });
    expect(ocultar).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(ocultar);
    expect(campo).toHaveAttribute("type", "password");
    expect(campo).toHaveValue("Segredo@123");
  });

  it("funciona pelo teclado (Enter e Espaço)", async () => {
    render(<Formulario />);
    const campo = screen.getByLabelText("Senha");
    await userEvent.click(campo);
    await userEvent.tab();
    expect(screen.getByRole("button", { name: "Mostrar senha" })).toHaveFocus();

    await userEvent.keyboard("{Enter}");
    expect(campo).toHaveAttribute("type", "text");
    await userEvent.keyboard(" ");
    expect(campo).toHaveAttribute("type", "password");
  });

  it("volta a ocultar e desabilita o botão quando o campo é desabilitado", async () => {
    const { rerender } = render(<Formulario />);
    await userEvent.click(screen.getByRole("button", { name: "Mostrar senha" }));
    expect(screen.getByLabelText("Senha")).toHaveAttribute("type", "text");

    rerender(<Formulario disabled />);
    expect(screen.getByLabelText("Senha")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Mostrar senha" })).toBeDisabled();
  });
});
