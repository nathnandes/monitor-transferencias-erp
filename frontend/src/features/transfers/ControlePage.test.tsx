import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getAnomalias,
  getLimites,
  getPainelControle,
  getPrazos,
  getTratativas,
  salvarPrazos,
} from "../../services/controleTransferenciasService";
import { getEmpresas } from "../../services/empresasService";
import { authFalso, renderComSessao, usuarioTeste } from "../../test/sessao";
import type { EmpresaResumo, PainelControle, TransferenciaRefControle } from "../../types/api";
import { ControlePage, TITULO_CONTROLE } from "./ControlePage";

vi.mock("../../services/controleTransferenciasService", () => ({
  getPainelControle: vi.fn(),
  getAnomalias: vi.fn(),
  getPrazos: vi.fn(),
  salvarPrazos: vi.fn(),
  getLimites: vi.fn(),
  salvarLimites: vi.fn(),
  getTratativas: vi.fn(),
  registrarTratativa: vi.fn(),
}));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));

const SEM_EXECUCAO = { execucao: null, analisadas: 0, sinalizadas: 0, lista: [] };
const RODADA = {
  concluida_em: "2026-10-12T14:00:00Z",
  status: "sucesso" as const,
  notas_treino: 4166,
  notas_avaliadas: 12,
  notas_sinalizadas: 1,
  mensagem: null,
};

const loja = (codigo: string): EmpresaResumo => ({ id: Number(codigo), codigo, nome: `Loja ${codigo}` });

function ref(id: number, parcial: Partial<TransferenciaRefControle> = {}): TransferenciaRefControle {
  return {
    id,
    numero_nota: String(1000 + id),
    origem: loja("1"),
    destino: loja("2"),
    status: "PROCESSADA",
    data_criacao: "2026-10-12T14:00:00Z",
    valor_total: "100.00",
    usuario_emissao: "MARIA",
    tratativa: null,
    ...parcial,
  };
}

function painel(): PainelControle {
  return {
    filtros: { empresa: null, data_inicial: null, data_final: null },
    resumo: {
      em_transito_quantidade: 3,
      em_transito_valor: "4520.10",
      fora_do_prazo: 2,
      divergentes: 1,
      valor_divergencia: "37.50",
      problemas_fiscais: 1,
      sem_tratativa: 3,
    },
    em_transito: [{ empresa: loja("2"), quantidade: 3, valor: "4520.10", mais_antiga: "2026-10-11T10:00:00Z" }],
    rotas: [
      {
        origem: loja("1"),
        destino: loja("2"),
        prazo_horas: 24,
        prazo_padrao: true,
        enviadas: 12,
        recebidas: 10,
        pendentes: 2,
        fora_do_prazo: 2,
        divergentes: 1,
        valor_enviado: "9000.00",
        tempo_medio_horas: 7.5,
      },
    ],
    divergencias: [
      {
        transferencia: ref(7),
        valor_diferenca: "37.50",
        itens: [
          {
            id_produto: "10",
            descricao: "CIMENTO FICTICIO",
            enviada: "5.0000",
            recebida: "4.0000",
            diferenca: "1.0000",
            valor_diferenca: "37.50",
            sem_saida: false,
          },
        ],
      },
    ],
    fiscal: [{ transferencia: ref(8), tipo: "CFOP_SAIDA", detalhe: "CFOP de saída 5102." }],
    emissores: [{ usuario: "MARIA", enviadas: 12, fora_do_prazo: 2, divergentes: 1, problemas_fiscais: 1 }],
    prazo_padrao_horas: 24,
    cfops_saida: ["5152"],
    cfops_entrada: ["1152"],
  };
}

beforeEach(() => {
  vi.mocked(getPainelControle).mockResolvedValue(painel());
  vi.mocked(getAnomalias).mockResolvedValue(SEM_EXECUCAO);
  vi.mocked(getPrazos).mockResolvedValue({ prazo_padrao_horas: 24, prazos: [] });
  vi.mocked(getLimites).mockResolvedValue({ horas_atencao: 24, horas_critico: 48, definido_por: null, atualizado_em: null });
  vi.mocked(getEmpresas).mockResolvedValue([]);
  vi.mocked(getTratativas).mockResolvedValue([]);
});

describe("ControlePage: fora do padrão", () => {
  const abrir = () => renderComSessao(<ControlePage />, { rota: "/transferencias/controle" });

  it("mostra a nota sinalizada com o motivo, sem acusar ninguém", async () => {
    vi.mocked(getAnomalias).mockResolvedValue({
      execucao: RODADA,
      analisadas: 834,
      sinalizadas: 1,
      lista: [
        {
          transferencia: ref(77, { numero_nota: "900077", usuario_emissao: "FULANO" }),
          score: 0.66,
          limiar: 0.54,
          motivos: ["faltaram 22% da quantidade enviada"],
          avaliada_em: "2026-10-12T14:00:00Z",
        },
      ],
    });
    abrir();

    expect(await screen.findByText("faltaram 22% da quantidade enviada")).toBeInTheDocument();
    expect(screen.getByText("900077")).toBeInTheDocument();
    expect(screen.getByText(/1 de 834 notas avaliadas/)).toBeInTheDocument();
    expect(screen.getByText(/não significa erro nem fraude/)).toBeInTheDocument();
    expect(screen.queryByText("FULANO")).not.toBeInTheDocument();
  });

  it("avisa quando o detector ainda não rodou", async () => {
    abrir();
    expect(await screen.findByText("O detector ainda não rodou")).toBeInTheDocument();
  });

  it("explica quando falta histórico", async () => {
    vi.mocked(getAnomalias).mockResolvedValue({
      ...SEM_EXECUCAO,
      execucao: { ...RODADA, status: "sem_historico", mensagem: "10 notas de histórico; o mínimo é 500." },
    });
    abrir();
    expect(await screen.findByText(/o mínimo é 500/)).toBeInTheDocument();
    expect(screen.getByText("Nenhuma nota sinalizada no período")).toBeInTheDocument();
  });

  it("não derruba o controle quando a consulta falha", async () => {
    vi.mocked(getAnomalias).mockRejectedValue(new Error("falhou"));
    abrir();
    expect(await screen.findByText("Não foi possível carregar as anomalias")).toBeInTheDocument();
    expect(screen.getByText("CIMENTO FICTICIO")).toBeInTheDocument();
  });
});

describe("ControlePage", () => {
  it("mostra o resumo, a rota, as divergências, o fiscal e o emissor", async () => {
    renderComSessao(<ControlePage />, { rota: "/transferencias/controle" });

    expect(screen.getByRole("heading", { level: 1, name: TITULO_CONTROLE })).toBeInTheDocument();
    expect(await screen.findAllByText("R$ 4.520,10")).not.toHaveLength(0);
    expect(screen.getByText("CIMENTO FICTICIO")).toBeInTheDocument();
    expect(screen.getByText("enviou 5, recebeu 4")).toBeInTheDocument();
    expect(screen.getByText("CFOP de saída 5102.")).toBeInTheDocument();
    expect(screen.getByText("2 fora do prazo")).toBeInTheDocument();
    expect(screen.getAllByText("MARIA").length).toBeGreaterThan(0);
  });

  it("operador vê os prazos, mas não altera", async () => {
    renderComSessao(<ControlePage />, { rota: "/transferencias/controle" });
    const campo = await screen.findByLabelText(/1 → 2/);
    expect(campo).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Salvar/ })).not.toBeInTheDocument();
  });

  it("admin define o prazo de uma rota", async () => {
    vi.mocked(salvarPrazos).mockResolvedValue({ prazo_padrao_horas: 24, prazos: [{ origem: "1", destino: "2", horas: 48 }] });
    const admin = authFalso(["TRANSFERENCIAS"], usuarioTeste({ role: "ADMIN" }));
    renderComSessao(<ControlePage />, { rota: "/transferencias/controle", auth: admin });

    await userEvent.type(await screen.findByLabelText(/1 → 2/), "48");
    await userEvent.click(screen.getByRole("button", { name: "Salvar (1)" }));
    await waitFor(() => expect(salvarPrazos).toHaveBeenCalledWith([{ origem: "1", destino: "2", horas: 48 }]));
  });

  it("cada número abre a lista de transferências já filtrada", async () => {

    window.history.replaceState(null, "", "/transferencias/controle?empresa=1&periodo=mes");
    renderComSessao(<ControlePage />, { rota: "/transferencias/controle?empresa=1&periodo=mes" });
    await screen.findByText("CIMENTO FICTICIO");
    const href = (nome: string | RegExp) => screen.getByRole("link", { name: nome }).getAttribute("href");


    expect(href("Fora do prazo")).toBe("/transferencias?empresa=1&periodo=mes&ocorrencia=FORA_DO_PRAZO");
    expect(href("Divergências")).toBe("/transferencias?empresa=1&periodo=mes&ocorrencia=DIVERGENTE");
    expect(href("Problemas fiscais")).toBe("/transferencias?empresa=1&periodo=mes&ocorrencia=FISCAL");
    expect(href("Sem tratativa")).toBe("/transferencias?empresa=1&periodo=mes&ocorrencia=SEM_TRATATIVA");
    expect(href("Em trânsito")).toBe("/transferencias?empresa=1&periodo=tudo&status=PENDENTE");
    expect(href(/R\$\s4\.520,10/)).toBe("/transferencias?empresa=1&periodo=tudo&empresa_destino=2&status=PENDENTE");


    expect(href("12 notas de Loja 1 para Loja 2")).toBe(
      "/transferencias?empresa=1&periodo=mes&empresa_origem=1&empresa_destino=2",
    );
    expect(href("2 fora do prazo")).toBe(
      "/transferencias?empresa=1&periodo=mes&empresa_origem=1&empresa_destino=2&ocorrencia=FORA_DO_PRAZO",
    );
    expect(href("1007")).toBe("/transferencias?empresa=1&periodo=mes&ocorrencia=DIVERGENTE&detalhe=7");
    expect(href("1008")).toBe("/transferencias?empresa=1&periodo=mes&ocorrencia=FISCAL&detalhe=8");
    const maria = screen.getAllByRole("link", { name: "MARIA" }).map((l) => l.getAttribute("href"));
    expect(new Set(maria)).toEqual(new Set(["/transferencias?empresa=1&periodo=mes&emitida_por=MARIA"]));
  });

  it("falha ao atualizar avisa e mantém os dados anteriores na tela", async () => {
    renderComSessao(<ControlePage />, { rota: "/transferencias/controle" });
    expect(await screen.findByText("CIMENTO FICTICIO")).toBeInTheDocument();
    vi.mocked(getPainelControle).mockRejectedValue(new Error("tempo esgotado"));

    await userEvent.click(screen.getByRole("button", { name: "Atualizar" }));

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent(/mostrando os dados anteriores/i);
    expect(aviso).toHaveTextContent("tempo esgotado");
    expect(screen.getByText("CIMENTO FICTICIO")).toBeInTheDocument();
  });
});
