

import { env } from "../lib/env";

export type TipoErroApi = "rede" | "timeout" | "http" | "resposta_invalida";

export class ApiError extends Error {
  readonly tipo: TipoErroApi;

  readonly status: number | null;

  readonly corpo: unknown;

  constructor(message: string, tipo: TipoErroApi, status: number | null = null, corpo: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.tipo = tipo;
    this.status = status;
    this.corpo = corpo;
  }
}

interface ConfiguracaoAuth {

  obterToken: () => string | null;

  aoRecusarToken: (tokenEnviado: string) => void;
}

const SEM_AUTH: ConfiguracaoAuth = { obterToken: () => null, aoRecusarToken: () => {} };
let auth: ConfiguracaoAuth = SEM_AUTH;


export function configurarAutenticacao(config: ConfiguracaoAuth): () => void {
  auth = config;
  return () => {
    if (auth === config) auth = SEM_AUTH;
  };
}


export const TIMEOUT_PADRAO_MS = 15_000;

type ValorParam = string | number | boolean | null | undefined;

export type Params = Record<string, ValorParam | readonly string[]>;

export interface OpcoesRequisicao {
  params?: Params;
  signal?: AbortSignal;
  timeoutMs?: number;

  autenticado?: boolean;

  token?: string;
}


export function montarQuery(params: Params = {}): string {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    for (const v of Array.isArray(valor) ? valor : [valor]) {
      if (v === undefined || v === null || v === "") continue;
      busca.append(chave, String(v));
    }
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

export function montarUrl(caminho: string, params?: Params): string {
  return `${env.apiBaseUrl}${caminho}${montarQuery(params)}`;
}


function mensagemDoCorpo(corpo: unknown): string | null {
  if (!corpo || typeof corpo !== "object" || !("detail" in corpo)) return null;
  const { detail } = corpo as { detail: unknown };
  if (typeof detail === "string") return detail;

  if (detail && typeof detail === "object" && "mensagem" in detail && typeof detail.mensagem === "string") {
    return detail.mensagem;
  }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : null))
      .filter(Boolean);
    return msgs.length ? msgs.join("; ") : null;
  }
  return null;
}

function ehAbort(erro: unknown): boolean {
  return erro instanceof DOMException && erro.name === "AbortError";
}

async function requisitar<T>(
  metodo: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  caminho: string,
  corpoEnvio: unknown,
  opcoes: OpcoesRequisicao,

  ler?: (resposta: Response) => Promise<T>,
): Promise<T> {
  const { params, signal, timeoutMs = TIMEOUT_PADRAO_MS, autenticado = true } = opcoes;
  const token = autenticado ? (opcoes.token ?? auth.obterToken()) : null;
  const headers: Record<string, string> = { Accept: ler ? "*/*" : "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (corpoEnvio !== undefined) headers["Content-Type"] = "application/json";


  const controle = new AbortController();
  let estourou = false;
  const cancelarPorChamador = () => controle.abort();
  if (signal?.aborted) controle.abort();
  signal?.addEventListener("abort", cancelarPorChamador, { once: true });
  const temporizador = setTimeout(() => {
    estourou = true;
    controle.abort();
  }, timeoutMs);

  try {
    let resposta: Response;
    try {
      resposta = await fetch(montarUrl(caminho, params), {
        method: metodo,
        headers,
        body: corpoEnvio === undefined ? undefined : JSON.stringify(corpoEnvio),
        signal: controle.signal,
      });
    } catch (erro) {
      if (estourou) {
        throw new ApiError(
          `A API não respondeu em ${Math.round(timeoutMs / 1000)} s. Verifique se o backend está em execução.`,
          "timeout",
        );
      }
      if (ehAbort(erro)) throw erro;
      throw new ApiError(
        "Não foi possível conectar à API. Verifique se o backend está em execução e se VITE_API_URL está correto.",
        "rede",
      );
    }

    if (!resposta.ok) {
      let corpo: unknown = null;
      try {
        corpo = await resposta.json();
      } catch {
        // Falha ignorada de propósito.
      }

      if (resposta.status === 401 && token) auth.aoRecusarToken(token);
      throw new ApiError(
        mensagemDoCorpo(corpo) ?? `A API respondeu com erro HTTP ${resposta.status}.`,
        "http",
        resposta.status,
        corpo,
      );
    }

    if (resposta.status === 204) return undefined as T;
    if (ler) return await ler(resposta);

    try {
      return (await resposta.json()) as T;
    } catch {
      throw new ApiError("A API devolveu uma resposta que não é JSON.", "resposta_invalida", resposta.status);
    }
  } finally {
    clearTimeout(temporizador);
    signal?.removeEventListener("abort", cancelarPorChamador);
  }
}

export function getJson<T>(caminho: string, opcoes: OpcoesRequisicao = {}): Promise<T> {
  return requisitar<T>("GET", caminho, undefined, opcoes);
}

export function postJson<T>(caminho: string, corpo?: unknown, opcoes: OpcoesRequisicao = {}): Promise<T> {
  return requisitar<T>("POST", caminho, corpo ?? {}, opcoes);
}

export function patchJson<T>(caminho: string, corpo: unknown, opcoes: OpcoesRequisicao = {}): Promise<T> {
  return requisitar<T>("PATCH", caminho, corpo, opcoes);
}

export function putJson<T>(caminho: string, corpo: unknown, opcoes: OpcoesRequisicao = {}): Promise<T> {
  return requisitar<T>("PUT", caminho, corpo, opcoes);
}


export function deleteJson<T = void>(caminho: string, opcoes: OpcoesRequisicao = {}): Promise<T> {
  return requisitar<T>("DELETE", caminho, undefined, opcoes);
}

export interface ArquivoBaixado {
  nome: string;

  total: number | null;
}


function nomeDoArquivo(resposta: Response, padrao: string): string {
  const cabecalho = resposta.headers.get("Content-Disposition") ?? "";
  return /filename="?([^";]+)"?/.exec(cabecalho)?.[1] ?? padrao;
}


export async function baixarArquivo(
  caminho: string,
  params: Params = {},
  nomePadrao = "arquivo.csv",
): Promise<ArquivoBaixado> {
  const { blob, nome, total } = await requisitar(
    "GET",
    caminho,
    undefined,
    { params, timeoutMs: 120_000 },
    async (resposta) => ({
      blob: await resposta.blob(),
      nome: nomeDoArquivo(resposta, nomePadrao),
      total: resposta.headers.has("X-Total-Registros") ? Number(resposta.headers.get("X-Total-Registros")) : null,
    }),
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return { nome, total };
}
