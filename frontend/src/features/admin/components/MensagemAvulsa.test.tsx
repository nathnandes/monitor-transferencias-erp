

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelarMensagemAvulsa,
  criarMensagemAvulsa,
  listarMensagensAvulsas,
  listarVariaveisMensagem,
  previaMensagemAvulsa,
} from "../../../services/alertasConfigService";
import type { DestinoAlerta, MensagemAvulsa as Mensagem } from "../../../types/api";
import { descreverDias } from "../lib/diasSemana";
import { MensagemAvulsa } from "./MensagemAvulsa";

vi.mock("../../../services/alertasConfigService", () => ({
  listarMensagensAvulsas: vi.fn(),
  criarMensagemAvulsa: vi.fn(),
  cancelarMensagemAvulsa: vi.fn(),
  listarVariaveisMensagem: vi.fn(),
  previaMensagemAvulsa: vi.fn(),
  listarModelosMensagemAvulsa: vi.fn(async () => []),
  salvarModeloMensagemAvulsa: vi.fn(),
  excluirModeloMensagemAvulsa: vi.fn(),
}));

const TODOS = [1, 2, 3, 4, 5, 6, 7];

const DESTINOS = [
  { id: 1, nome: "Gerente", canal: "whatsapp", chat_id: "5511999990000", ativo: true, severidade_minima: "WARNING", empresas: [] },
  { id: 2, nome: "Grupo Depósito", canal: "telegram", chat_id: "-1001", ativo: true, severidade_minima: "WARNING", empresas: [] },
  { id: 3, nome: "Antigo", canal: "whatsapp", chat_id: "5511988880000", ativo: false, severidade_minima: "WARNING", empresas: [] },
] as DestinoAlerta[];

function agendada(parcial: Partial<Mensagem> = {}): Mensagem {
  return {
    id: 7,
    texto: "Inventário amanhã às 7h",
    agendada_para: "2026-11-06T12:00:00Z",
    horario: null,
    dias_semana: [],
    criada_por: "Admin",
    criada_em: "2026-11-05T12:00:00Z",
    cancelada_em: null,
    envios: [
      { destino_id: 1, destino_nome: "Gerente", canal: "whatsapp", status: "PENDENTE", enviada_em: null, ultimo_erro: null },
    ],
    ...parcial,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listarMensagensAvulsas).mockResolvedValue([]);
  vi.mocked(criarMensagemAvulsa).mockResolvedValue(agendada());
  vi.mocked(cancelarMensagemAvulsa).mockResolvedValue(agendada({ cancelada_em: "2026-11-05T13:00:00Z" }));
  vi.mocked(listarVariaveisMensagem).mockResolvedValue([
    { chave: "faturamento_liquido", rotulo: "Faturamento líquido de hoje", exemplo: "R$ 1,00" },
    { chave: "recebido", rotulo: "Recebido hoje", exemplo: "R$ 2,00" },
  ]);
  vi.mocked(previaMensagemAvulsa).mockImplementation(async (texto) => ({
    texto: texto.replace("{faturamento_liquido}", "R$ 47.890,90"),
  }));
});

describe("MensagemAvulsa", () => {
  it("envia agora o texto para os destinos marcados", async () => {
    const aoConcluir = vi.fn();
    const usuario = userEvent.setup();
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={aoConcluir} />);

    await usuario.type(screen.getByLabelText("Mensagem"), "Reunião às 8h");
    await usuario.click(screen.getByRole("checkbox", { name: /Gerente/ }));
    await usuario.click(screen.getByRole("button", { name: "Enviar agora" }));

    expect(criarMensagemAvulsa).toHaveBeenCalledWith({
      texto: "Reunião às 8h",
      destinos: [1],
      agendada_para: null,
      horario: null,
      dias_semana: TODOS,
    });
    expect(aoConcluir).toHaveBeenCalledWith("Mensagem na fila para envio.");
    await waitFor(() => expect(listarMensagensAvulsas).toHaveBeenCalledTimes(2));
  });

  it("não mostra destino desligado", () => {
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={vi.fn()} />);
    expect(screen.queryByRole("checkbox", { name: /Antigo/ })).toBeNull();
  });

  it("agendada manda a data e hora escolhidas, sem fuso", async () => {
    const usuario = userEvent.setup();
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={vi.fn()} />);

    await usuario.type(screen.getByLabelText("Mensagem"), "Fechamento");
    await usuario.click(screen.getByRole("checkbox", { name: /Grupo Depósito/ }));
    await usuario.click(screen.getByRole("radio", { name: "Em uma data e hora" }));
    await usuario.click(screen.getByRole("button", { name: "Agendar mensagem" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Escolha a data e a hora.");
    expect(criarMensagemAvulsa).not.toHaveBeenCalled();

    await usuario.type(screen.getByLabelText("Data e hora do envio"), "2030-01-02T08:30");
    await usuario.click(screen.getByRole("button", { name: "Agendar mensagem" }));
    expect(criarMensagemAvulsa).toHaveBeenCalledWith(
      expect.objectContaining({ texto: "Fechamento", destinos: [2], agendada_para: "2030-01-02T08:30:00", horario: null }),
    );
  });

  it("programa todo dia, no horário e nos dias marcados, com valor inserido pelo botão", async () => {
    const aoConcluir = vi.fn();
    const usuario = userEvent.setup();
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={aoConcluir} />);

    await usuario.type(screen.getByLabelText("Mensagem"), "Líquido: ");
    await usuario.click(await screen.findByRole("button", { name: "Inserir Faturamento líquido de hoje" }));
    expect(screen.getByLabelText("Mensagem")).toHaveValue("Líquido: {faturamento_liquido}");
    await waitFor(() =>
      expect(screen.getByLabelText("Prévia da mensagem")).toHaveTextContent("Líquido: R$ 47.890,90"),
    );

    await usuario.click(screen.getByRole("checkbox", { name: /Gerente/ }));
    await usuario.click(screen.getByRole("radio", { name: "Todo dia, num horário" }));
    await usuario.clear(screen.getByLabelText("Horário do envio"));
    await usuario.type(screen.getByLabelText("Horário do envio"), "19:30");
    await usuario.click(screen.getByRole("checkbox", { name: "domingo" }));
    await usuario.click(screen.getByRole("button", { name: "Programar mensagem" }));

    expect(criarMensagemAvulsa).toHaveBeenCalledWith({
      texto: "Líquido: {faturamento_liquido}",
      destinos: [1],
      agendada_para: null,
      horario: "19:30",
      dias_semana: [1, 2, 3, 4, 5, 6],
    });
    expect(aoConcluir).toHaveBeenCalledWith("Mensagem programada de segunda a sábado às 19:30.");
  });

  it("sem texto ou sem destino não chama o backend", async () => {
    const usuario = userEvent.setup();
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={vi.fn()} />);
    await usuario.click(screen.getByRole("button", { name: "Enviar agora" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Escreva a mensagem.");
    await usuario.type(screen.getByLabelText("Mensagem"), "oi");
    await usuario.click(screen.getByRole("button", { name: "Enviar agora" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Escolha pelo menos um destino.");
    expect(criarMensagemAvulsa).not.toHaveBeenCalled();
  });

  it("lista as mensagens e cancela a que ainda está na fila", async () => {
    vi.mocked(listarMensagensAvulsas).mockResolvedValue([agendada()]);
    const usuario = userEvent.setup();
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={vi.fn()} />);

    expect(await screen.findByText("Inventário amanhã às 7h")).toBeInTheDocument();
    expect(screen.getByText("Gerente: Na fila")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: /Cancelar mensagem:/ }));
    await usuario.click(screen.getByRole("button", { name: "Cancelar envio" }));
    expect(cancelarMensagemAvulsa).toHaveBeenCalledWith(7);
  });

  it("repetida mostra o horário, o próximo envio e o botão Parar", async () => {
    vi.mocked(listarMensagensAvulsas).mockResolvedValue([
      agendada({ id: 9, horario: "18:00:00", dias_semana: [1, 2, 3, 4, 5], envios: [] }),
    ]);
    const usuario = userEvent.setup();
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={vi.fn()} />);

    expect(await screen.findByText("De segunda a sexta às 18:00")).toBeInTheDocument();
    expect(screen.getByText(/próximo envio:/)).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: /Parar mensagem:/ }));
    await usuario.click(screen.getByRole("button", { name: "Parar envios" }));
    expect(cancelarMensagemAvulsa).toHaveBeenCalledWith(9);
  });

  it("enviada não tem botão de cancelar", async () => {
    vi.mocked(listarMensagensAvulsas).mockResolvedValue([
      agendada({
        envios: [
          { destino_id: 1, destino_nome: "Gerente", canal: "whatsapp", status: "ENVIADA", enviada_em: "2026-11-06T12:00:30Z", ultimo_erro: null },
        ],
      }),
    ]);
    render(<MensagemAvulsa destinos={DESTINOS} aoConcluir={vi.fn()} />);
    expect(await screen.findByText("Gerente: Enviada")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancelar mensagem:/ })).toBeNull();
  });
});

describe("descreverDias", () => {
  it("resume os dias marcados", () => {
    expect(descreverDias(TODOS)).toBe("todo dia");
    expect(descreverDias([1, 2, 3, 4, 5])).toBe("de segunda a sexta");
    expect(descreverDias([1, 3, 5])).toBe("seg, qua e sex");
  });
});
