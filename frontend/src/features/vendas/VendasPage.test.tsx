import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/apiClient";
import { getEmpresas } from "../../services/empresasService";
import { exportarDescontos, exportarFormasPagamento, getResumoVendas } from "../../services/vendasService";
import { resumoVendas as resumo, totaisVendas as totais } from "../../test/factories";
import type { Empresa } from "../../types/api";
import { authFalso, renderComSessao } from "../../test/sessao";
import { nomeCurtoEmpresa } from "../../lib/format";
import { hojeNoFuso } from "../../lib/periodo";
import { prepararSerie } from "./lib/vendas";
import { TITULO_VENDAS, VendasPage } from "./VendasPage";

vi.mock("../../services/vendasService", () => ({ getResumoVendas: vi.fn(), exportarFormasPagamento: vi.fn(), exportarDescontos: vi.fn() }));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));

const empresaCompleta = (codigo: string, nome: string): Empresa => ({
  id: Number(codigo),
  codigo,
  nome,
  bairro: null,
  id_erp: null,
  ativo: true,
  ambiente: "development",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

const auth = () => authFalso(["VENDAS"]);
const ultimosParams = () => vi.mocked(getResumoVendas).mock.calls.at(-1)![0];

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/vendas");
  vi.mocked(getEmpresas).mockResolvedValue([]);
  vi.mocked(getResumoVendas).mockResolvedValue(resumo());
});

describe("VendasPage", () => {
  it("mostra os indicadores com a variação contra a comparação", async () => {
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    expect(screen.getByRole("heading", { level: 1, name: TITULO_VENDAS })).toBeInTheDocument();

    const faturamento = (await screen.findByRole("heading", { name: "Faturamento líquido" })).closest("article")!;
    expect(within(faturamento).getByText("R$ 120.000,00")).toBeInTheDocument();
    expect(within(faturamento).getByText("Bruto R$ 125.430,90")).toBeInTheDocument();
    expect(within(faturamento).getByText("▲ 20%")).toBeInTheDocument();
    const devolucoes = screen.getByRole("heading", { name: "Devoluções" }).closest("article")!;
    expect(within(devolucoes).getByText("R$ 5.430,90")).toBeInTheDocument();
    expect(within(devolucoes).getByText("4,3% do faturamento bruto")).toBeInTheDocument();
    const notas = screen.getByRole("heading", { name: "Notas de venda" }).closest("article")!;
    expect(within(notas).getByText("300")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ticket médio" }).closest("article")).toHaveTextContent("R$ 418,10");

    expect(ultimosParams()).toMatchObject({ data_inicial: expect.any(String), comparar_inicial: expect.any(String) });
    expect(ultimosParams()).not.toHaveProperty("canal", expect.anything());
  });

  it("mostra canais, lojas e os produtos mais vendidos", async () => {
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    expect(await screen.findByText("CIMENTO FICTICIO 50KG")).toBeInTheDocument();
    expect(screen.getByText("Faturamento logística")).toBeInTheDocument();
    expect(screen.getByText("79,7%")).toBeInTheDocument();
    expect(screen.getByTitle("Empresa 1")).toHaveTextContent("1 · Empresa 1");

    expect(screen.getByTitle("PIX TEF")).toHaveTextContent("Pix tef");
    expect(screen.getByText("60,0%")).toBeInTheDocument();
  });

  it("ranqueia os vendedores e mostra quem está abaixo da média", async () => {
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    const painel = (await screen.findByRole("heading", { name: "Vendedores" })).closest("section")!;
    expect(within(painel).getByText("R$ 41.810,30")).toBeInTheDocument();
    const linhas = within(painel).getAllByRole("row").slice(1);
    expect(linhas.map((l) => within(l).getAllByRole("cell")[1]!.textContent)).toEqual([
      "Maria da Silva SouzaCód. 633 · Loja 1",
      "Joao dos SantosCód. 22 · Loja 1",
      "Vendedor 16055Cód. 16055 · Loja 1",
    ]);

    expect(within(linhas[0]!).getByText("191,3%")).toBeInTheDocument();
    expect(within(linhas[1]!).getByText("71,8%")).toBeInTheDocument();
    expect(linhas[1]).toHaveTextContent("abaixo da média");
    expect(within(linhas[0]!).getByText("▲ 33%")).toBeInTheDocument();
    expect(within(linhas[2]!).getByText("▲ novo")).toBeInTheDocument();
    expect(within(painel).getByText(/2 notas sem vendedor/)).toBeInTheDocument();

    await userEvent.click(within(painel).getByRole("button", { name: "Abaixo da média" }));
    expect(within(painel).getAllByRole("row").slice(1)).toHaveLength(2);
    expect(within(painel).queryByText("Maria da Silva Souza")).not.toBeInTheDocument();
  });

  it("com filtro de canal, devoluções e formas de pagamento não se aplicam", async () => {
    vi.mocked(getResumoVendas).mockResolvedValue(
      resumo({ totais: totais("25430.90", 250, null), comparacao: null, formas_pagamento: null }),
    );
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    const faturamento = (await screen.findByRole("heading", { name: "Faturamento" })).closest("article")!;
    expect(within(faturamento).getByText("R$ 25.430,90")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Devoluções" }).closest("article")).toHaveTextContent(
      "Não se aplica ao filtro de canal",
    );
    expect(screen.getByText(/recebimentos não têm canal/)).toBeInTheDocument();
  });

  it("exporta as formas de pagamento em Excel com os filtros da tela", async () => {
    vi.mocked(exportarFormasPagamento).mockResolvedValue();
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
    await screen.findByText("CIMENTO FICTICIO 50KG");

    await userEvent.click(screen.getByRole("button", { name: "Excel" }));

    expect(exportarFormasPagamento).toHaveBeenCalledWith(ultimosParams());
  });

  describe("relatório de descontos", () => {
    const abrir = async () => {
      await screen.findByText("CIMENTO FICTICIO 50KG");
      await userEvent.click(screen.getByRole("button", { name: "Descontos" }));
      return screen.getByRole("form", { name: "Relatório de descontos" });
    };

    it("baixa o Excel do período digitado, com o canal da tela", async () => {
      vi.mocked(exportarDescontos).mockResolvedValue();
      window.history.replaceState(null, "", "/vendas?canal=balcao");
      renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas?canal=balcao" });
      const form = await abrir();

      const de = within(form).getByLabelText("De");
      const ate = within(form).getByLabelText("Até");
      await userEvent.clear(de);
      await userEvent.type(de, "2026-10-01");
      await userEvent.clear(ate);
      await userEvent.type(ate, "2026-10-31");
      await userEvent.click(within(form).getByRole("button", { name: "Baixar Excel" }));

      expect(exportarDescontos).toHaveBeenCalledWith(
        expect.objectContaining({ data_inicial: "2026-10-01", data_final: "2026-10-31", canal: "balcao" }),
      );
    });

    it("mês passado preenche do primeiro ao último dia", async () => {
      renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
      const form = await abrir();

      await userEvent.click(within(form).getByRole("button", { name: "Mês passado" }));

      const inicio = (within(form).getByLabelText("De") as HTMLInputElement).value;
      const fim = (within(form).getByLabelText("Até") as HTMLInputElement).value;
      expect(inicio.endsWith("-01")).toBe(true);
      expect(inicio.slice(0, 7)).toBe(fim.slice(0, 7));
      expect(new Date(`${fim}T00:00:00Z`).getUTCDate()).toBeGreaterThanOrEqual(28);
      expect(fim < hojeNoFuso()).toBe(true);
    });

    it("não baixa com a data inicial depois da final", async () => {
      renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
      const form = await abrir();

      const de = within(form).getByLabelText("De");
      const ate = within(form).getByLabelText("Até");
      await userEvent.clear(ate);
      await userEvent.type(ate, "2026-10-01");
      await userEvent.clear(de);
      await userEvent.type(de, "2026-10-31");

      expect(within(form).getByRole("alert")).toHaveTextContent("depois da final");
      expect(within(form).getByRole("button", { name: "Baixar Excel" })).toBeDisabled();
    });

    it("mostra o erro da API", async () => {
      vi.mocked(exportarDescontos).mockRejectedValue(new Error("Escolha um período menor."));
      renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
      const form = await abrir();

      await userEvent.click(within(form).getByRole("button", { name: "Baixar Excel" }));

      expect(await within(form).findByRole("alert")).toHaveTextContent("Escolha um período menor.");
    });
  });

  it("filtra pelo canal: vai para a URL e para a API", async () => {
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
    await screen.findByText("CIMENTO FICTICIO 50KG");

    await userEvent.click(within(screen.getByRole("group", { name: "Canal de venda" })).getByRole("button", { name: "Balcão" }));

    await waitFor(() => expect(ultimosParams()).toMatchObject({ canal: "balcao" }));
    expect(window.location.search).toContain("canal=balcao");
    expect(screen.getByRole("button", { name: "Balcão" })).toHaveAttribute("aria-pressed", "true");
  });

  it("escolhe os últimos N sábados: substituem o período e a comparação", async () => {
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
    await screen.findByText("CIMENTO FICTICIO 50KG");

    await userEvent.click(screen.getByRole("button", { name: "Escolher dias" }));
    const quantidade = screen.getByRole("spinbutton", { name: "Quantidade de dias" });
    await userEvent.clear(quantidade);
    await userEvent.type(quantidade, "3");
    await userEvent.click(screen.getByRole("button", { name: "Aplicar" }));

    await waitFor(() => expect(ultimosParams()).toHaveProperty("dias"));
    const dias = ultimosParams()!.dias!.split(",");
    expect(dias).toHaveLength(3);
    expect(dias.every((d) => new Date(`${d}T00:00:00Z`).getUTCDay() === 6)).toBe(true);
    expect(ultimosParams()).not.toHaveProperty("data_inicial", expect.anything());
    expect(ultimosParams()).not.toHaveProperty("comparar_inicial", expect.anything());
    expect(window.location.search).toContain("dias=");
    expect(screen.getAllByText(/3 sábados/).length).toBeGreaterThan(0);


    const grupo = screen.getByRole("group", { name: "Dias escolhidos" });
    await userEvent.click(within(grupo).getAllByRole("button", { name: /^Tirar/ })[0]!);
    await waitFor(() => expect(ultimosParams()!.dias!.split(",")).toEqual(dias.slice(1)));


    await userEvent.click(within(screen.getByRole("group", { name: "Período" })).getByRole("button", { name: "Mês" }));
    await waitFor(() => expect(ultimosParams()).not.toHaveProperty("dias", expect.anything()));
    expect(window.location.search).not.toContain("dias=");
  });

  it("avisa quando o período começa antes do histórico já carregado", async () => {
    vi.mocked(getResumoVendas).mockResolvedValue(
      resumo({
        filtro: { ...resumo().filtro, data_inicial: "2026-10-01" },
        cobertura: { desde: "2026-10-05", ate: "2026-10-10", atualizado_em: null },
      }),
    );
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    expect(await screen.findByText(/histórico de vendas ainda está sendo carregado/)).toBeInTheDocument();
  });

  it("sem vendas no período, os gráficos dizem isso em vez de desenhar zero", async () => {
    vi.mocked(getResumoVendas).mockResolvedValue(
      resumo({ totais: totais("0", 0), comparacao: null, por_canal: [], por_categoria: [], por_empresa: [], produtos: [] }),
    );
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    expect((await screen.findAllByText("Nenhuma venda no período.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Ticket médio" }).closest("article")).toHaveTextContent("—");
  });

  it("tem a aba Geral e uma aba por empresa, que filtra pela empresa", async () => {
    vi.mocked(getEmpresas).mockResolvedValue([
      empresaCompleta("01", "Rede Exemplo Matriz"),
      empresaCompleta("03", "Rede Exemplo Loja Norte"),
    ]);
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    const abas = await screen.findByRole("tablist", { name: "Vendas por empresa" });
    expect(within(abas).getByRole("tab", { name: "Geral" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(await within(abas).findByRole("tab", { name: "Loja Norte" }));

    expect(within(abas).getByRole("tab", { name: "Loja Norte" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(ultimosParams()).toMatchObject({ empresa: "03" }));
    expect(window.location.search).toContain("empresa=03");

    await userEvent.click(within(abas).getByRole("tab", { name: "Geral" }));
    await waitFor(() => expect(ultimosParams()).not.toHaveProperty("empresa", expect.anything()));
  });

  it("o perfil escolhe as abas: sem a Geral, abre na loja liberada e o seletor não tem consolidado", async () => {
    vi.mocked(getEmpresas).mockResolvedValue([
      empresaCompleta("01", "Rede Exemplo Matriz"),
      empresaCompleta("02", "Rede Exemplo Loja Norte"),
      empresaCompleta("03", "Rede Exemplo Loja Sul"),
    ]);
    const comPerfil = authFalso(["VENDAS"], undefined, ["VENDAS.EMPRESA_2", "VENDAS.EMPRESA_3"]);
    renderComSessao(<VendasPage />, { auth: comPerfil, rota: "/vendas" });

    const abas = await screen.findByRole("tablist", { name: "Vendas por empresa" });
    await waitFor(() =>
      expect(within(abas).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Loja Norte", "Loja Sul"]),
    );
    await waitFor(() => expect(window.location.search).toContain("empresa=02"));
    expect(within(abas).getByRole("tab", { name: "Loja Norte" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(ultimosParams()).toMatchObject({ empresa: "02" }));
    expect(screen.queryByRole("option", { name: /Consolidado/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Matriz/ })).not.toBeInTheDocument();

    expect(screen.queryByRole("link", { name: /Modo TV/ })).not.toBeInTheDocument();

    expect(vi.mocked(getResumoVendas).mock.calls.every(([p]) => p?.empresa === "02")).toBe(true);
  });

  it("falha da API aparece nos painéis, com tentar de novo", async () => {
    vi.mocked(getResumoVendas).mockRejectedValue(new ApiError("Sem conexão com a API", "rede"));
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });

    expect((await screen.findAllByText(/Falha ao carregar: Evolução do faturamento/)).length).toBe(1);
  });

  it("falha ao atualizar avisa e mantém os dados anteriores na tela", async () => {
    renderComSessao(<VendasPage />, { auth: auth(), rota: "/vendas" });
    expect(await screen.findByRole("heading", { name: "Ticket médio" })).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(getResumoVendas)).toHaveBeenCalled());
    await screen.findAllByText(/120.000,00/);
    vi.mocked(getResumoVendas).mockRejectedValue(new ApiError("Sem conexão com a API", "rede"));

    await userEvent.click(screen.getByRole("button", { name: "Atualizar" }));

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent(/mostrando os dados anteriores/i);
    expect(screen.getAllByText(/120.000,00/).length).toBeGreaterThan(0);
  });
});

describe("nomeCurtoEmpresa", () => {
  it("tira o prefixo comum das lojas e mantém nomes fora do padrão", () => {
    expect(nomeCurtoEmpresa("Rede Exemplo Loja Norte")).toBe("Loja Norte");
    expect(nomeCurtoEmpresa("Rede Exemplo")).toBe("Rede Exemplo");
    expect(nomeCurtoEmpresa("Empresa 1")).toBe("Empresa 1");
  });
});

describe("prepararSerie", () => {
  it("rotula meses e, quando a série cruza anos, inclui o ano", () => {
    const serie = prepararSerie(
      [
        { chave: "2025-12", faturamento: "10.5", notas: 1, quantidade: "2", devolucoes: "0.5" },
        { chave: "2026-01", faturamento: "20", notas: 2, quantidade: "3.5", devolucoes: null },
      ],
      "mes",
    );
    expect(serie.map((p) => [p.rotulo, p.rotuloCompleto, p.faturamento, p.quantidade, p.devolucoes, p.liquido])).toEqual([
      ["dez/25", "dezembro de 2025", 10.5, 2, 0.5, 10],
      ["jan/26", "janeiro de 2026", 20, 3.5, null, 20],
    ]);
  });

  it("rotula dias como dd/mm", () => {
    const [ponto] = prepararSerie([{ chave: "2026-10-08", faturamento: "1", notas: 1, quantidade: "1", devolucoes: "0" }], "dia");
    expect([ponto!.rotulo, ponto!.rotuloCompleto]).toEqual(["08/10", "08/10/2026"]);
  });
});
