import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { ChartPanel } from "./charts/ChartPanel";
import { ApiError } from "../services/apiClient";
import { Header } from "./layout/Header";
import { Dica } from "./ui/Dica";
import { ErrorState } from "./ui/ErrorState";
import { MetricCard } from "./ui/MetricCard";
import { Modal } from "./ui/Modal";


function PaginaComModal() {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setAberto(true)}>
        Abrir
      </button>
      <a href="#x">link da página</a>
      <Modal aberto={aberto} titulo="Detalhe" aoFechar={() => setAberto(false)}>
        <button type="button">Primeira ação</button>
        <button type="button">Última ação</button>
      </Modal>
    </>
  );
}

describe("Modal — foco e fechamento", () => {
  it("move o foco para o diálogo, prende o Tab dentro e deixa o fundo inerte", async () => {
    const { container } = render(<PaginaComModal />);
    await userEvent.click(screen.getByRole("button", { name: "Abrir" }));

    const dialogo = screen.getByRole("dialog", { name: "Detalhe" });
    expect(dialogo).toHaveAttribute("aria-modal", "true");
    expect(dialogo).toHaveFocus();

    expect(container).toHaveAttribute("inert");
    expect(dialogo.closest("[inert]")).toBeNull();

    const fechar = within(dialogo).getByRole("button", { name: "Fechar detalhes" });
    const ultima = within(dialogo).getByRole("button", { name: "Última ação" });
    await userEvent.tab();
    expect(fechar).toHaveFocus();
    await userEvent.tab();
    await userEvent.tab();
    expect(ultima).toHaveFocus();
    await userEvent.tab();
    expect(fechar).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(ultima).toHaveFocus();
  });

  it("Esc fecha, libera o fundo e devolve o foco a quem abriu", async () => {
    const { container } = render(<PaginaComModal />);
    const abrir = screen.getByRole("button", { name: "Abrir" });
    await userEvent.click(abrir);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(container).not.toHaveAttribute("inert");
    expect(abrir).toHaveFocus();
  });

  it("o botão Fechar fecha", async () => {
    render(<PaginaComModal />);
    await userEvent.click(screen.getByRole("button", { name: "Abrir" }));
    await userEvent.click(screen.getByRole("button", { name: "Fechar detalhes" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Header — atualização em andamento", () => {
  it("sinaliza aria-busy, troca o rótulo e ignora cliques repetidos sem perder o foco", async () => {
    const atualizar = vi.fn();
    const { rerender } = render(<Header titulo="T" subtitulo="Contexto operacional" selo={null} aoAtualizar={atualizar} atualizando />);
    expect(screen.getByText("Contexto operacional")).toBeInTheDocument();
    const botao = screen.getByRole("button", { name: "Atualizando…" });
    expect(botao).toHaveAttribute("aria-busy", "true");
    expect(botao).toHaveAttribute("aria-disabled", "true");
    expect(botao).toBeEnabled();
    await userEvent.click(botao);
    expect(atualizar).not.toHaveBeenCalled();

    rerender(<Header titulo="T" selo={null} aoAtualizar={atualizar} />);
    await userEvent.click(screen.getByRole("button", { name: "Atualizar" }));
    expect(atualizar).toHaveBeenCalledOnce();
  });
});

describe("Dica (tooltip)", () => {
  it("abre no foco, descreve o botão e fecha com Esc", async () => {
    render(<Dica sobre="Pendentes" texto="Transferências com status PENDENTE." />);
    const botao = screen.getByRole("button", { name: "Sobre: Pendentes" });
    expect(botao).toHaveAccessibleDescription("Transferências com status PENDENTE.");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    await userEvent.tab();
    expect(botao).toHaveFocus();
    expect(screen.getByRole("tooltip")).toHaveTextContent("Transferências com status PENDENTE.");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("MetricCard oferece a dica sem mudar o rótulo do card", () => {
    render(<MetricCard rotulo="Erros" valor="5" dica="Status ERRO." />);
    expect(screen.getByRole("heading", { name: "Erros" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sobre: Erros" })).toBeInTheDocument();
  });
});

describe("ErrorState — tipo de falha", () => {
  it.each([
    [new ApiError("Não foi possível conectar à API.", "rede"), "Sem conexão com a API"],
    [new ApiError("A API não respondeu em 15 s.", "timeout"), "Tempo de resposta esgotado"],
    [new ApiError("A API respondeu com erro HTTP 500.", "http", 500), "Erro da API · HTTP 500"],
    [new ApiError("A API devolveu uma resposta que não é JSON.", "resposta_invalida", 200), "Resposta inválida da API"],
  ])("distingue %s", (erro, rotulo) => {
    render(<ErrorState erro={erro} />);
    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent(rotulo);
    expect(alerta).toHaveTextContent(erro.message);
  });

  it("erro genérico não ganha selo de tipo", () => {
    render(<ErrorState erro={new Error("falhou")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("falhou");
    expect(screen.queryByText("Erro inesperado")).not.toBeInTheDocument();
  });
});

describe("ChartPanel — atualização", () => {
  it("mantém o gráfico e mostra 'Atualizando' numa recarga", () => {
    render(
      <ChartPanel titulo="Por status" carregando={false} atualizando erro={null} vazio={false} aoTentarNovamente={() => {}}>
        <p>gráfico</p>
      </ChartPanel>,
    );
    expect(screen.getByText("gráfico")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Atualizando");
    expect(screen.getByRole("figure", { name: "Por status" })).toHaveAttribute("aria-busy", "true");
  });
});
