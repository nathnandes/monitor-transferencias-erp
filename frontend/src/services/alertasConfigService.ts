

import type {
  ConfiguracaoAlertas,
  DestinoAlertaEntrada,
  MensagemAvulsa,
  MensagemAvulsaEntrada,
  ModeloMensagemAvulsa,
  PreviaModelo,
  RegraAlertaEntrada,
  VariavelModelo,
} from "../types/api";
import { deleteJson, getJson, postJson, putJson } from "./apiClient";

export const CAMINHO_CONFIG_ALERTAS = "/api/v1/admin/alertas";

const caminhoRegra = (regra: string) => `${CAMINHO_CONFIG_ALERTAS}/regras/${encodeURIComponent(regra)}`;
const caminhoDestino = (id: number) => `${CAMINHO_CONFIG_ALERTAS}/destinos/${id}`;
const caminhoModelo = (chave: string) => `${CAMINHO_CONFIG_ALERTAS}/modelos/${encodeURIComponent(chave)}`;

export function getConfiguracaoAlertas(signal?: AbortSignal): Promise<ConfiguracaoAlertas> {
  return getJson<ConfiguracaoAlertas>(CAMINHO_CONFIG_ALERTAS, { signal });
}

export function salvarRegraAlerta(regra: string, dados: RegraAlertaEntrada): Promise<ConfiguracaoAlertas> {
  return putJson<ConfiguracaoAlertas>(caminhoRegra(regra), dados);
}


export function restaurarRegraAlerta(regra: string): Promise<ConfiguracaoAlertas> {
  return deleteJson<ConfiguracaoAlertas>(caminhoRegra(regra));
}

export function criarDestinoAlerta(dados: DestinoAlertaEntrada): Promise<ConfiguracaoAlertas> {
  return postJson<ConfiguracaoAlertas>(`${CAMINHO_CONFIG_ALERTAS}/destinos`, dados);
}

export function editarDestinoAlerta(id: number, dados: DestinoAlertaEntrada): Promise<ConfiguracaoAlertas> {
  return putJson<ConfiguracaoAlertas>(caminhoDestino(id), dados);
}


export function excluirDestinoAlerta(id: number): Promise<ConfiguracaoAlertas> {
  return deleteJson<ConfiguracaoAlertas>(caminhoDestino(id));
}


export function salvarModeloMensagem(chave: string, texto: string): Promise<ConfiguracaoAlertas> {
  return putJson<ConfiguracaoAlertas>(caminhoModelo(chave), { texto });
}

export function restaurarModeloMensagem(chave: string): Promise<ConfiguracaoAlertas> {
  return deleteJson<ConfiguracaoAlertas>(caminhoModelo(chave));
}


export function previaModeloMensagem(chave: string, texto: string, signal?: AbortSignal): Promise<PreviaModelo> {
  return postJson<PreviaModelo>(`${caminhoModelo(chave)}/previa`, { texto }, { signal });
}



const CAMINHO_MENSAGENS = `${CAMINHO_CONFIG_ALERTAS}/mensagens`;


export function listarMensagensAvulsas(signal?: AbortSignal): Promise<MensagemAvulsa[]> {
  return getJson<MensagemAvulsa[]>(CAMINHO_MENSAGENS, { signal });
}


export function criarMensagemAvulsa(dados: MensagemAvulsaEntrada): Promise<MensagemAvulsa> {
  return postJson<MensagemAvulsa>(CAMINHO_MENSAGENS, dados);
}


export function cancelarMensagemAvulsa(id: number): Promise<MensagemAvulsa> {
  return deleteJson<MensagemAvulsa>(`${CAMINHO_MENSAGENS}/${id}`);
}


export function listarVariaveisMensagem(signal?: AbortSignal): Promise<VariavelModelo[]> {
  return getJson<VariavelModelo[]>(`${CAMINHO_MENSAGENS}/variaveis`, { signal });
}


export function previaMensagemAvulsa(texto: string, signal?: AbortSignal): Promise<PreviaModelo> {
  return postJson<PreviaModelo>(`${CAMINHO_MENSAGENS}/previa`, { texto }, { signal });
}


export function listarModelosMensagemAvulsa(signal?: AbortSignal): Promise<ModeloMensagemAvulsa[]> {
  return getJson<ModeloMensagemAvulsa[]>(`${CAMINHO_MENSAGENS}/modelos`, { signal });
}


export function salvarModeloMensagemAvulsa(nome: string, texto: string): Promise<ModeloMensagemAvulsa[]> {
  return postJson<ModeloMensagemAvulsa[]>(`${CAMINHO_MENSAGENS}/modelos`, { nome, texto });
}

export function excluirModeloMensagemAvulsa(id: number): Promise<ModeloMensagemAvulsa[]> {
  return deleteJson<ModeloMensagemAvulsa[]>(`${CAMINHO_MENSAGENS}/modelos/${id}`);
}
