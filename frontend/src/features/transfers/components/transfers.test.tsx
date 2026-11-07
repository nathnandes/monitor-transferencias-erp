import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Pagination } from "../../../components/ui/Pagination";
import type { EstadoAsync } from "../../../hooks/useAsync";
import { ApiError } from "../../../services/apiClient";
import { getTransferencia } from "../../../services/transferenciasService";
import { detalhe, pagina, transferencia, transferenciaCoiErrado } from "../../../test/factories";
import { FILTROS_VAZIOS, type Empresa, type PaginaTransferencias } from "../../../types/api";
import { CONSULTA_INICIAL } from "../lib/queryFilters";
import { FilterBar } from "./FilterBar";
import { TransferDetailView, TransferDetails } from "./TransferDetails";
import { TransfersPanel } from "./TransfersPanel";
import { TransfersTable } from "./TransfersTable";

vi.mock("../../../services/transferenciasService", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../services/transferenciasService")>()),
  getTransferencia: vi.fn(),
}));

const semAcao = () => {};

const empresas: Empresa[] = ["01", "02"].map((codigo, i) => ({
  id: i + 1,
  codigo,
  nome: `Empresa ${codigo}`,
  bairro: null,
  id_erp: `DEMO-EMP-${codigo}`,
  ativo: true,
  ambiente: "development",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
}));

describe("FilterBar", () => {
  const props = {
    empresas,
    carregandoEmpresas: false,
    opcoesStatus: ["PENDENTE", "PROCESSADA", "ERRO"],
    aplicados: FILTROS_VAZIOS,
    aoLimpar: semAcao,
  };

  it("empresas vêm da prop (API) e nada é aplicado antes de clicar em Aplicar", async () => {
    const aplicar = vi.fn();
    render(<FilterBar {...props} aoAplicar={aplicar} />);
    const origem = screen.getByLabelText("Saiu de");
    expect(within(origem).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Todas",
      "01 — Empresa 01",
      "02 — Empresa 02",
    ]);

    await userEvent.selectOptions(origem, "01");
    await userEvent.selectOptions(screen.getByLabelText("Situação"), "ERRO");
    expect(aplicar).not.toHaveBeenCalled();
    expect(screen.getByText("Há alterações não aplicadas.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    expect(aplicar).toHaveBeenCalledOnce();
    expect(aplicar).toHaveBeenCalledWith({ ...FILTROS_VAZIOS, empresa_origem: "01", status: "ERRO" });
  });

  it("filtra pela situação do COI e mostra o chip com o rótulo legível", async () => {
    const aplicar = vi.fn();
    const { rerender } = render(<FilterBar {...props} aoAplicar={aplicar} />);
    await userEvent.selectOptions(screen.getByLabelText("COI"), "ERRADO");
    await userEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    expect(aplicar).toHaveBeenCalledWith({ ...FILTROS_VAZIOS, situacao_coi: "ERRADO" });

    rerender(<FilterBar {...props} aplicados={{ ...FILTROS_VAZIOS, situacao_coi: "ERRADO" }} aoAplicar={aplicar} />);
    expect(within(screen.getByRole("list", { name: "Filtros aplicados" })).getByText("COI: COI errado")).toBeInTheDocument();
  });

  it("Limpar zera o rascunho e avisa o pai", async () => {
    const limpar = vi.fn();
    render(<FilterBar {...props} aplicados={{ ...FILTROS_VAZIOS, status: "ERRO" }} aoAplicar={semAcao} aoLimpar={limpar} />);
    expect(screen.getByLabelText("Situação")).toHaveValue("ERRO");
    await userEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(limpar).toHaveBeenCalledOnce();
    expect(screen.getByLabelText("Situação")).toHaveValue("");
  });
});

describe("FilterBar — filtros ativos", () => {
  it("mostra chips removíveis dos filtros aplicados, com rótulos legíveis", async () => {
    const aplicar = vi.fn();
    render(
      <FilterBar
        empresas={empresas}
        carregandoEmpresas={false}
        opcoesStatus={["PENDENTE", "PROCESSADA", "ERRO"]}
        aplicados={{ ...FILTROS_VAZIOS, empresa_origem: "01", status: "ERRO" }}
        aoAplicar={aplicar}
        aoLimpar={semAcao}
      />,
    );
    expect(screen.getByRole("search", { name: "Filtrar a lista" })).toBeInTheDocument();
    const chips = screen.getByRole("list", { name: "Filtros aplicados" });
    expect(within(chips).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Saiu de: 01 — Empresa 01",
      "Situação: Erro",
    ]);

    expect(screen.queryByLabelText(/período/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remover filtro Situação: Erro" }));
    expect(aplicar).toHaveBeenCalledWith({ ...FILTROS_VAZIOS, empresa_origem: "01" });
  });

  it("sem filtros: sem chips e Limpar desabilitado", () => {
    render(
      <FilterBar
        empresas={empresas}
        carregandoEmpresas={false}
        opcoesStatus={[]}
        aplicados={FILTROS_VAZIOS}
        aoAplicar={semAcao}
        aoLimpar={semAcao}
      />,
    );
    expect(screen.queryByRole("list", { name: "Filtros aplicados" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Limpar filtros" })).toBeDisabled();
  });
});

describe("TransfersTable", () => {
  it("mostra nota, quando saiu e chegou, rota, quem emitiu, valor, itens e Ver detalhes", async () => {
    const abrir = vi.fn();
    render(
      <TransfersTable
        aoAbrir={abrir}
        itens={[
          transferencia({
            id: 7,
            id_erp: "DEMO-TRF-0007",
            status: "PROCESSADA",
            quantidade_itens: 4,
            data_criacao: "2026-09-20T15:00:00Z",
            data_processamento: "2026-09-21T13:30:00Z",
            usuario_emissao: "MARIA",
            valor_total: "1520.50",
          }),
        ]}
      />,
    );
    const linha = screen.getByText("DEMO-TRF-0007").closest("tr")!;
    expect(within(linha).getByText("Recebida")).toBeInTheDocument();
    expect(within(linha).getByText("20/09/2026, 11:00")).toBeInTheDocument();
    expect(within(linha).getByText("chegou 21/09/2026, 09:30")).toBeInTheDocument();
    expect(within(linha).getByText("MARIA")).toBeInTheDocument();
    expect(within(linha).getByText(/1\.520,50/)).toBeInTheDocument();
    expect(within(linha).getByText("4")).toBeInTheDocument();
    await userEvent.click(within(linha).getByRole("button", { name: "Ver detalhes da transferência DEMO-TRF-0007" }));
    expect(abrir).toHaveBeenCalledWith(7);
  });

  it("cada célula tem rótulo para o modo cartão, oculto do leitor de tela", () => {
    render(<TransfersTable aoAbrir={semAcao} itens={[transferencia({ id: 7, id_erp: "DEMO-TRF-0007" })]} />);
    const linha = screen.getByText("DEMO-TRF-0007").closest("tr")!;
    const rotulos = within(linha).getAllByText(/^(Nota|Saiu em|De → Para|Emitida por|Valor|Itens|Situação)$/);
    expect(rotulos).toHaveLength(7);
    for (const r of rotulos) expect(r).toHaveAttribute("aria-hidden", "true");
    expect(screen.getAllByRole("columnheader")).toHaveLength(8);
  });

  it("destaca a linha da transferência com COI errado; as demais não levam o selo", () => {
    render(
      <TransfersTable
        aoAbrir={semAcao}
        itens={[
          transferenciaCoiErrado(),
          transferencia({ id: 8, id_erp: "DEMO-TRF-0008", coi: "8044", coi_entrada: "7161", situacao_coi: "CORRETO" }),
        ]}
      />,
    );
    const semCoi = screen.getByText("DEMO-TRF-0004").closest("tr")!;
    expect(semCoi).toHaveAttribute("data-sem-coi", "true");
    expect(within(semCoi).getByText("COI errado")).toBeInTheDocument();

    const comCoi = screen.getByText("DEMO-TRF-0008").closest("tr")!;
    expect(comCoi).not.toHaveAttribute("data-sem-coi");
    expect(within(comCoi).queryByText("COI errado")).not.toBeInTheDocument();
  });
});

describe("Pipeline e COI no detalhe", () => {
  it("transferência com COI errado: aviso com o problema e etapa do COI com falha", () => {
    render(<TransferDetailView transferencia={{ ...detalhe(), ...transferenciaCoiErrado() }} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/COI errado/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/nota de entrada sem COI/);
    const etapas = within(screen.getByRole("list", { name: "Etapas da transferência" })).getAllByRole("listitem");
    expect(etapas.map((e) => e.dataset.etapa)).toEqual(["criada", "processamento", "coi", "concluida"]);
    expect(etapas.map((e) => e.dataset.estado)).toEqual(["concluida", "concluida", "falha", "pendente"]);
    expect(screen.getByText("7163")).toBeInTheDocument();
  });

  it("transferência com COIs certos: sem aviso e os COIs aparecem", () => {
    render(<TransferDetailView transferencia={detalhe({ coi: "8044", coi_entrada: "7161", situacao_coi: "CORRETO" })} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("8044")).toBeInTheDocument();
    expect(screen.getByText("7161")).toBeInTheDocument();
    expect(screen.getByText("COIs certos")).toBeInTheDocument();
  });

  it("etapa em andamento é marcada como a atual", () => {
    render(<TransferDetailView transferencia={detalhe({ status: "PENDENTE", etapas: transferencia().etapas })} />);
    const atual = within(screen.getByRole("list", { name: "Etapas da transferência" }))
      .getAllByRole("listitem")
      .find((e) => e.getAttribute("aria-current") === "step");
    expect(atual?.dataset.etapa).toBe("processamento");
  });
});

describe("Pagination", () => {
  it("mostra página, total de páginas e registros; respeita os limites", async () => {
    const mudar = vi.fn();
    const { rerender } = render(
      <Pagination pagina={1} totalPaginas={3} totalRegistros={45} tamanhoPagina={20} itensNaPagina={20} aoMudarPagina={mudar} />,
    );
    const nav = screen.getByRole("navigation", { name: "Paginação" });
    expect(nav).toHaveTextContent("Exibindo 1–20 · 45 registros");
    expect(nav).toHaveTextContent("Página 1 de 3");
    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Próxima" }));
    expect(mudar).toHaveBeenCalledWith(2);

    rerender(<Pagination pagina={3} totalPaginas={3} totalRegistros={45} tamanhoPagina={20} itensNaPagina={5} aoMudarPagina={mudar} />);
    expect(nav).toHaveTextContent("Exibindo 41–45");
    expect(screen.getByRole("button", { name: "Próxima" })).toBeDisabled();
  });

  it("seletor de tamanho só oferece as opções dadas", async () => {
    const tamanho = vi.fn();
    render(
      <Pagination pagina={1} totalPaginas={1} totalRegistros={5} tamanhoPagina={20} itensNaPagina={5} aoMudarPagina={semAcao} opcoesTamanho={[10, 20, 50, 100]} aoMudarTamanho={tamanho} />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Por página"), "50");
    expect(tamanho).toHaveBeenCalledWith(50);
  });
});

function estado(parcial: Partial<EstadoAsync<PaginaTransferencias>>): EstadoAsync<PaginaTransferencias> {
  return { data: null, error: null, loading: false, atualizadoEm: null, recarregar: semAcao, ...parcial };
}

describe("TransfersPanel — estados", () => {
  const props = {
    consulta: CONSULTA_INICIAL,
    aoMudarPagina: semAcao,
    aoMudarTamanho: semAcao,
    aoAbrirDetalhe: semAcao,
    aoFecharDetalhe: semAcao,
    aoLimparFiltros: semAcao,
  };

  it("carregando", () => {
    render(<TransfersPanel {...props} tabela={estado({ loading: true })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Carregando transferências...");
  });

  it("erro com tentar novamente", async () => {
    const tentar = vi.fn();
    render(<TransfersPanel {...props} tabela={estado({ error: new Error("HTTP 500"), recarregar: tentar })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Não foi possível carregar as transferências");
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(tentar).toHaveBeenCalledOnce();
  });

  it("vazio com filtros oferece limpar", async () => {
    const limpar = vi.fn();
    render(
      <TransfersPanel
        {...props}
        consulta={{ ...CONSULTA_INICIAL, filtros: { ...FILTROS_VAZIOS, status: "ERRO" } }}
        aoLimparFiltros={limpar}
        tabela={estado({ data: pagina([]) })}
      />,
    );
    expect(screen.getByText("Nenhuma transferência encontrada")).toBeInTheDocument();
    expect(screen.getByText("Nenhum registro atende aos filtros aplicados.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(limpar).toHaveBeenCalledOnce();
  });

  it("página além do fim leva à última", async () => {
    const mudar = vi.fn();
    render(
      <TransfersPanel {...props} aoMudarPagina={mudar} tabela={estado({ data: pagina([], { total: 36, total_paginas: 2, pagina: 9 }) })} />,
    );
    expect(screen.getByText("A página 9 não existe")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ir para a última página" }));
    expect(mudar).toHaveBeenCalledWith(2);
  });
});

describe("TransferDetails", () => {
  beforeEach(() => {
    vi.mocked(getTransferencia).mockReset();
  });

  it("busca o detalhe ao abrir e devolve o foco ao fechar", async () => {
    vi.mocked(getTransferencia).mockResolvedValue(detalhe());
    const fechar = vi.fn();
    const { rerender } = render(
      <>
        <button type="button">origem</button>
        <TransferDetails id={null} aoFechar={fechar} />
      </>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(getTransferencia).not.toHaveBeenCalled();

    screen.getByRole("button", { name: "origem" }).focus();
    rerender(
      <>
        <button type="button">origem</button>
        <TransferDetails id={1} aoFechar={fechar} />
      </>,
    );
    const dialogo = screen.getByRole("dialog", { name: "Transferência #1" });
    expect(await within(dialogo).findByText("Produto A")).toBeInTheDocument();
    expect(getTransferencia).toHaveBeenCalledWith(1, expect.any(AbortSignal));

    await userEvent.keyboard("{Escape}");
    expect(fechar).toHaveBeenCalledOnce();
    rerender(
      <>
        <button type="button">origem</button>
        <TransferDetails id={null} aoFechar={fechar} />
      </>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "origem" })).toHaveFocus();
  });

  it("404 mostra mensagem clara e opção de voltar", async () => {
    vi.mocked(getTransferencia).mockImplementation(async () => {
      throw new ApiError("Transferência 999 não encontrada.", "http", 404);
    });
    const fechar = vi.fn();
    render(<TransferDetails id={999} aoFechar={fechar} />);
    expect(await screen.findByText("Transferência #999 não encontrada")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Voltar para a lista" }));
    expect(fechar).toHaveBeenCalledOnce();
  });

  it("outros erros mostram a mensagem e tentar novamente", async () => {
    vi.mocked(getTransferencia)
      .mockRejectedValueOnce(new ApiError("Não foi possível conectar à API.", "rede"))
      .mockResolvedValueOnce(detalhe());
    render(<TransferDetails id={1} aoFechar={semAcao} />);
    expect(await screen.findByText("Não foi possível conectar à API.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    await waitFor(() => expect(screen.getByText("Produto A")).toBeInTheDocument());
  });
});

describe("TransferDetailView", () => {
  it("destaca divergências com a diferença exata", () => {
    render(<TransferDetailView transferencia={detalhe()} />);
    expect(screen.getByText("Origem").parentElement).toHaveTextContent("01");
    expect(screen.getByText("Destino").parentElement).toHaveTextContent("02");
    expect(screen.getByText("1 item divergente")).toBeInTheDocument();
    expect(screen.getByText(/diferente da solicitada em 1 item/)).toBeInTheDocument();

    const linhaA = screen.getByText("Produto A").closest("tr")!;
    expect(linhaA).toHaveAttribute("data-divergente", "true");
    expect(within(linhaA).getByText("36")).toBeInTheDocument();
    expect(within(linhaA).getByText("35")).toBeInTheDocument();
    expect(within(linhaA).getByText("−1")).toBeInTheDocument();
    expect(within(linhaA).getByText("Divergente")).toBeInTheDocument();

    const linhaB = screen.getByText("Produto B").closest("tr")!;
    expect(linhaB).not.toHaveAttribute("data-divergente");
    expect(within(linhaB).getByText("Conferido")).toBeInTheDocument();
  });

  it("'Somente divergentes' reduz a lista de itens", async () => {
    render(<TransferDetailView transferencia={detalhe()} />);
    const botao = screen.getByRole("button", { name: "Somente divergentes" });
    expect(botao).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("Produto B")).toBeInTheDocument();

    await userEvent.click(botao);
    expect(botao).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Produto A")).toBeInTheDocument();
    expect(screen.queryByText("Produto B")).not.toBeInTheDocument();
  });

  it("tabela de itens mantém cabeçalhos e rótulos visuais não são lidos em dobro", () => {
    render(<TransferDetailView transferencia={detalhe()} />);
    const tabela = screen.getByRole("table");
    expect(within(tabela).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Produto",
      "Solicitada",
      "Processada",
      "Diferença",
      "Valor",
      "Situação",
    ]);

    const rotulos = within(tabela).getAllByText("Solicitada").filter((el) => el.tagName === "SPAN");
    expect(rotulos.length).toBeGreaterThan(0);
    for (const r of rotulos) expect(r).toHaveAttribute("aria-hidden");
  });

  it("nunca exibe raw_data, mesmo que a resposta traga o campo", () => {
    const comRaw = {
      ...detalhe(),
      raw_data: { segredo: "RAW-DATA-NAO-EXIBIR", aviso: "DADOS FICTICIOS" },
      itens: detalhe().itens.map((i) => ({ ...i, raw_data: { interno: "RAW-ITEM-NAO-EXIBIR" } })),
    };
    const { container } = render(<TransferDetailView transferencia={comRaw} />);
    expect(container).not.toHaveTextContent("RAW-DATA-NAO-EXIBIR");
    expect(container).not.toHaveTextContent("RAW-ITEM-NAO-EXIBIR");
    expect(container).not.toHaveTextContent("raw_data");
    expect(container).not.toHaveTextContent("DADOS FICTICIOS");
  });
});
