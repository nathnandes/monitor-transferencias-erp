

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../services/apiClient";
import {
  criarDestinoAlerta,
  excluirDestinoAlerta,
  getConfiguracaoAlertas,
  previaModeloMensagem,
  restaurarModeloMensagem,
  restaurarRegraAlerta,
  salvarModeloMensagem,
  salvarRegraAlerta,
} from "../../services/alertasConfigService";
import { getEmpresas } from "../../services/empresasService";
import { authFalso, renderComSessao, usuarioTeste } from "../../test/sessao";
import type { ConfiguracaoAlertas, ModeloMensagemAlerta, RegraAlertaConfig } from "../../types/api";
import { AdminAlertasPage, TITULO_ADMIN_ALERTAS } from "./AdminAlertasPage";

vi.mock("../../services/alertasConfigService", () => ({
  getConfiguracaoAlertas: vi.fn(),
  salvarRegraAlerta: vi.fn(),
  restaurarRegraAlerta: vi.fn(),
  criarDestinoAlerta: vi.fn(),
  editarDestinoAlerta: vi.fn(),
  excluirDestinoAlerta: vi.fn(),
  salvarModeloMensagem: vi.fn(),
  restaurarModeloMensagem: vi.fn(),
  previaModeloMensagem: vi.fn(),
  listarMensagensAvulsas: vi.fn(async () => []),
  criarMensagemAvulsa: vi.fn(),
  cancelarMensagemAvulsa: vi.fn(),
  listarVariaveisMensagem: vi.fn(async () => []),
  previaMensagemAvulsa: vi.fn(),
  listarModelosMensagemAvulsa: vi.fn(async () => []),
  salvarModeloMensagemAvulsa: vi.fn(),
  excluirModeloMensagemAvulsa: vi.fn(),
}));
vi.mock("../../services/empresasService", () => ({ getEmpresas: vi.fn() }));
vi.mock("../../services/estoqueBaixoService", () => ({
  getEstoqueBaixo: vi.fn(async () => ({
    configurado: false,
    ativo: false,
    dias_cobertura: 7,
    dias_por_empresa: {},
    janela_dias: 30,
    horarios: ["08:00"],
    ultima_execucao: null,
    atualizado_por: null,
    atualizado_em: null,
  })),
  getSituacaoEstoqueBaixo: vi.fn(async () => ({ lojas: [] })),
  salvarEstoqueBaixo: vi.fn(),
}));

function regra(parcial: Partial<RegraAlertaConfig> = {}): RegraAlertaConfig {
  return {
    regra: "transferencia_atrasada",
    tipo: "alerta",
    nome: "Transferência sem entrada no destino",
    descricao: "Nota de saída sem a entrada.",
    ativo: true,
    personalizada: false,
    campos_disponiveis: [
      { chave: "nota", rotulo: "Nota", padrao: true },
      { chave: "origem", rotulo: "Origem", padrao: true },
      { chave: "emitida_por", rotulo: "Emitida por", padrao: false },
    ],
    campos: ["nota", "origem"],
    destinos: [1],
    ...parcial,
  };
}

const PADRAO_AVISO = "{emoji} {titulo}\n\n{campos}";

function modelo(parcial: Partial<ModeloMensagemAlerta> = {}): ModeloMensagemAlerta {
  return {
    chave: "transferencia_atrasada:aviso",
    nome: "Transferência sem entrada no destino: aviso",
    grupo: "Transferência sem entrada no destino",
    descricao: "Quando o alerta abre ou agrava.",
    variaveis: [
      { chave: "titulo", rotulo: "Título do alerta", exemplo: "Transferência NF 1" },
      { chave: "nota", rotulo: "Nota", exemplo: "NF 1" },
    ],
    padrao: PADRAO_AVISO,
    texto: PADRAO_AVISO,
    personalizado: false,
    atualizado_por: null,
    atualizado_em: null,
    ...parcial,
  };
}

function config(parcial: Partial<ConfiguracaoAlertas> = {}): ConfiguracaoAlertas {
  return {
    regras: [regra()],
    destinos: [
      { id: 1, nome: "Padrão", canal: "telegram", chat_id: null, ativo: true, severidade_minima: "WARNING", empresas: [] },
      {
        id: 2,
        nome: "Gerência",
        canal: "telegram",
        chat_id: "-100222",
        ativo: true,
        severidade_minima: "CRITICAL",
        empresas: [10],
      },
      {
        id: 3,
        nome: "Celular do gerente",
        canal: "whatsapp",
        chat_id: "5511987654321",
        ativo: true,
        severidade_minima: "ERROR",
        empresas: [],
      },
    ],
    modelos: [
      modelo(),
      modelo({ chave: "resumo_diario", nome: "Resumo do dia", grupo: "Resumo do dia", texto: "Bom dia", padrao: "Bom dia" }),
    ],
    ...parcial,
  };
}

const auth = () => authFalso(["DASHBOARD", "ADMINISTRACAO"], usuarioTeste({ role: "ADMIN" }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getConfiguracaoAlertas).mockResolvedValue(config());
  vi.mocked(previaModeloMensagem).mockImplementation(async (_chave, texto) => ({ texto: `PRÉVIA ${texto}` }));
  vi.mocked(getEmpresas).mockResolvedValue([
    { id: 10, codigo: "5", nome: "Depósito 02", id_erp: "5", ativo: true, created_at: "", updated_at: "" } as never,
  ]);
});

describe("AdminAlertasPage", () => {
  it("lista os destinos com chat, empresas e severidade", async () => {
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    expect(screen.getByRole("heading", { level: 1, name: TITULO_ADMIN_ALERTAS })).toBeInTheDocument();
    expect(await screen.findByText(/chat do .env/)).toBeInTheDocument();
    expect(await screen.findByText(/-100222 · Empresas: 5 - Depósito 02/)).toBeInTheDocument();
    expect(screen.getByText("Só crítico")).toBeInTheDocument();
    expect(screen.getByText(/WhatsApp \+55 11 98765-4321 · Empresas: Todas/)).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Excluir destino Padrão" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Excluir destino Gerência" })).toBeInTheDocument();
  });

  it("salva destinos e campos de uma regra", async () => {
    vi.mocked(salvarRegraAlerta).mockResolvedValue(config({ regras: [regra({ personalizada: true })] }));
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    const painel = (await screen.findByText("Transferência sem entrada no destino")).closest("section")!;
    const salvar = within(painel).getByRole("button", { name: "Salvar" });
    expect(salvar).toBeDisabled();

    await userEvent.click(within(painel).getByRole("checkbox", { name: "Gerência" }));
    await userEvent.click(within(painel).getByRole("checkbox", { name: "Emitida por" }));
    await userEvent.click(within(painel).getByRole("checkbox", { name: "Origem" }));

    expect(within(painel).getByRole("link", { name: /Controle/ })).toHaveAttribute("href", "/transferencias/controle");

    expect(within(painel).getByText(/Emitida por:/)).toBeInTheDocument();
    expect(within(painel).queryByText(/Origem:/)).not.toBeInTheDocument();

    await userEvent.click(salvar);

    await waitFor(() =>
      expect(salvarRegraAlerta).toHaveBeenCalledWith("transferencia_atrasada", {
        ativo: true,
        campos: ["nota", "emitida_por"],
        destinos: [1, 2],
      }),
    );
    expect(await screen.findByText(/salvo\. Vale a partir do próximo ciclo/)).toBeInTheDocument();
  });

  it("mostra o erro de validação da API na regra", async () => {
    vi.mocked(salvarRegraAlerta).mockRejectedValue(
      new ApiError("Campo desconhecido para esta regra: x.", "http", 422),
    );
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    const painel = (await screen.findByText("Transferência sem entrada no destino")).closest("section")!;
    await userEvent.click(within(painel).getByRole("checkbox", { name: /Ligado/ }));
    await userEvent.click(within(painel).getByRole("button", { name: "Salvar" }));
    expect(await within(painel).findByRole("alert")).toHaveTextContent("Campo desconhecido");
  });

  it("volta a regra personalizada ao padrão", async () => {
    vi.mocked(getConfiguracaoAlertas).mockResolvedValue(config({ regras: [regra({ personalizada: true })] }));
    vi.mocked(restaurarRegraAlerta).mockResolvedValue(config());
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    await userEvent.click(await screen.findByRole("button", { name: /Voltar ao padrão/ }));
    expect(restaurarRegraAlerta).toHaveBeenCalledWith("transferencia_atrasada");
    expect(await screen.findByText(/voltou ao padrão/)).toBeInTheDocument();
  });

  it("cria um destino pelo formulário", async () => {
    vi.mocked(criarDestinoAlerta).mockResolvedValue(config());
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    await userEvent.click(await screen.findByRole("button", { name: "Novo destino" }));
    const dialogo = await screen.findByRole("dialog");
    await userEvent.type(within(dialogo).getByLabelText("Nome"), "Grupo Depósito");
    await userEvent.type(within(dialogo).getByLabelText("Chat do Telegram"), " -1001234 ");
    await userEvent.selectOptions(within(dialogo).getByLabelText("Recebe"), "ERROR");
    await userEvent.click(within(dialogo).getByRole("checkbox", { name: "5 - Depósito 02" }));
    await userEvent.click(within(dialogo).getByRole("button", { name: "Salvar destino" }));

    await waitFor(() =>
      expect(criarDestinoAlerta).toHaveBeenCalledWith({
        nome: "Grupo Depósito",
        canal: "telegram",
        chat_id: "-1001234",
        ativo: true,
        severidade_minima: "ERROR",
        empresas: [10],
      }),
    );
  });

  it("cria um destino no WhatsApp com o número", async () => {
    vi.mocked(criarDestinoAlerta).mockResolvedValue(config());
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    await userEvent.click(await screen.findByRole("button", { name: "Novo destino" }));
    const dialogo = await screen.findByRole("dialog");
    await userEvent.type(within(dialogo).getByLabelText("Nome"), "Celular da loja");
    await userEvent.selectOptions(within(dialogo).getByLabelText("Canal"), "whatsapp");
    await userEvent.type(within(dialogo).getByLabelText("Número do WhatsApp"), "+55 21 99999-0000");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Salvar destino" }));

    await waitFor(() =>
      expect(criarDestinoAlerta).toHaveBeenCalledWith({
        nome: "Celular da loja",
        canal: "whatsapp",
        chat_id: "+55 21 99999-0000",
        ativo: true,
        severidade_minima: "WARNING",
        empresas: [],
      }),
    );
  });

  it("excluir destino com histórico mostra o 409 da API", async () => {
    vi.mocked(excluirDestinoAlerta).mockRejectedValue(
      new ApiError("Este destino já recebeu alertas e fica no histórico: desligue-o em vez de excluir.", "http", 409),
    );
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    await userEvent.click(await screen.findByRole("button", { name: "Excluir destino Gerência" }));
    await userEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Excluir" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("desligue-o em vez de excluir");
  });

  it("edita o texto de uma mensagem com variável, prévia e salvar", async () => {
    vi.mocked(salvarModeloMensagem).mockResolvedValue(
      config({ modelos: [modelo({ texto: "{nota} parada", personalizado: true, atualizado_por: "Admin" })] }),
    );
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    const painel = (await screen.findByRole("heading", { name: "Mensagens do Telegram" })).closest("section")!;
    const texto = within(painel).getByLabelText("Texto");
    expect(texto).toHaveValue(PADRAO_AVISO);

    await userEvent.clear(texto);
    await userEvent.click(within(painel).getByRole("button", { name: "Inserir Nota" }));


    await waitFor(() => expect(texto).toHaveFocus());
    await userEvent.type(texto, " parada");
    expect(texto).toHaveValue("{nota} parada");


    expect(await within(painel).findByText("PRÉVIA {nota} parada", {}, { timeout: 3000 })).toBeInTheDocument();

    await userEvent.click(within(painel).getByRole("button", { name: "Salvar mensagem" }));
    expect(salvarModeloMensagem).toHaveBeenCalledWith("transferencia_atrasada:aviso", "{nota} parada");
    expect(await within(painel).findByText(/Personalizada por Admin/)).toBeInTheDocument();
  });

  it("mostra o erro de variável desconhecida na prévia e volta a mensagem ao padrão", async () => {
    vi.mocked(getConfiguracaoAlertas).mockResolvedValue(
      config({ modelos: [modelo({ texto: "{nota}", personalizado: true, atualizado_por: "Admin" })] }),
    );
    vi.mocked(previaModeloMensagem).mockRejectedValue(
      new ApiError("Variável que esta mensagem não tem: {xyz}.", "http", 422),
    );
    vi.mocked(restaurarModeloMensagem).mockResolvedValue(config());
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    const painel = (await screen.findByRole("heading", { name: "Mensagens do Telegram" })).closest("section")!;

    expect(await within(painel).findByText(/não tem: \{xyz\}/, {}, { timeout: 3000 })).toBeInTheDocument();
    await userEvent.click(within(painel).getByRole("button", { name: /Voltar ao texto padrão/ }));
    expect(restaurarModeloMensagem).toHaveBeenCalledWith("transferencia_atrasada:aviso");
    await waitFor(() => expect(within(painel).getByLabelText("Texto")).toHaveValue(PADRAO_AVISO));
  });

  it("separa os tipos de alerta do uso do sistema", async () => {
    vi.mocked(getConfiguracaoAlertas).mockResolvedValue(
      config({
        regras: [
          regra(),
          regra({ regra: "login", tipo: "atividade", nome: "Entrada no sistema", ativo: false, destinos: [] }),
        ],
      }),
    );
    renderComSessao(<AdminAlertasPage />, { auth: auth() });
    const uso = (await screen.findByRole("heading", { name: "Uso do sistema" })).closest("section")!;
    expect(within(uso).getByText("Entrada no sistema")).toBeInTheDocument();
    expect(within(uso).queryByText("Transferência sem entrada no destino")).not.toBeInTheDocument();
    const alertas = screen.getByRole("heading", { name: "Tipos de alerta" }).closest("section")!;
    expect(within(alertas).queryByText("Entrada no sistema")).not.toBeInTheDocument();
  });
});
