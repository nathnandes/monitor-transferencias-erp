

import type { OcorrenciaControle, Severidade, SituacaoCoi, StatusSincronizacao, StatusTransferencia } from "../types/api";

export type Tom = "bom" | "aviso" | "serio" | "critico" | "neutro" | "info";


export const COR_TOM: Record<Tom, string> = {
  bom: "#16a34a",
  aviso: "#f39c12",
  serio: "#ec835a",
  critico: "#dc2626",
  info: "#2563eb",
  neutro: "#898781",
};

export const STATUS_CONHECIDOS = ["PENDENTE", "PROCESSADA", "ERRO"] as const satisfies readonly StatusTransferencia[];


const TOM_STATUS: Record<StatusTransferencia, Tom> = {
  PROCESSADA: "bom",
  PENDENTE: "aviso",
  ERRO: "critico",
  CANCELADA: "neutro",
};

export const SEM_STATUS = "SEM STATUS";


const ROTULO_STATUS: Record<StatusTransferencia, string> = {
  PENDENTE: "A caminho",
  PROCESSADA: "Recebida",
  CANCELADA: "Cancelada",
  ERRO: "Erro",
};

export function rotuloDoStatus(status: string | null | undefined): string {
  const normalizado = normalizarStatus(status);
  return ehChaveDe(ROTULO_STATUS, normalizado) ? ROTULO_STATUS[normalizado] : normalizado;
}

export function normalizarStatus(status: string | null | undefined): string {
  const texto = status?.trim().toUpperCase();
  return texto ? texto : SEM_STATUS;
}

function ehChaveDe<K extends string>(mapa: Record<K, unknown>, valor: string): valor is K {
  return Object.hasOwn(mapa, valor);
}

export function tomDoStatus(status: string | null | undefined): Tom {
  const normalizado = normalizarStatus(status);
  return ehChaveDe(TOM_STATUS, normalizado) ? TOM_STATUS[normalizado] : "neutro";
}


export const SEVERIDADES = ["INFO", "WARNING", "ERROR", "CRITICAL"] as const;

const TOM_SEVERIDADE: Record<Severidade, Tom> = {
  INFO: "info",
  WARNING: "aviso",
  ERROR: "serio",
  CRITICAL: "critico",
};

export function tomDaSeveridade(severidade: string): Tom {
  const chave = severidade.toUpperCase();
  return ehChaveDe(TOM_SEVERIDADE, chave) ? TOM_SEVERIDADE[chave] : "neutro";
}


export const SITUACOES_COI = ["ERRADO", "CORRETO", "AGUARDANDO"] as const satisfies readonly SituacaoCoi[];

export const ROTULO_SITUACAO_COI: Record<SituacaoCoi, string> = {
  ERRADO: "COI errado",
  CORRETO: "COIs certos",
  AGUARDANDO: "Aguardando entrada",
};

export const TOM_SITUACAO_COI: Record<SituacaoCoi, Tom> = {
  ERRADO: "critico",
  CORRETO: "bom",
  AGUARDANDO: "neutro",
};


export const OCORRENCIAS = ["FORA_DO_PRAZO", "DIVERGENTE", "FISCAL", "SEM_TRATATIVA"] as const satisfies readonly OcorrenciaControle[];

export const ROTULO_OCORRENCIA: Record<OcorrenciaControle, string> = {
  FORA_DO_PRAZO: "Fora do prazo",
  DIVERGENTE: "Divergência de quantidade",
  FISCAL: "Problema fiscal",
  SEM_TRATATIVA: "Sem tratativa",
};

const TOM_SINCRONIZACAO: Record<StatusSincronizacao, Tom> = {
  sucesso: "bom",
  parcial: "aviso",
  erro: "critico",
  em_andamento: "info",
};

export function tomDaSincronizacao(status: string): Tom {
  return ehChaveDe(TOM_SINCRONIZACAO, status) ? TOM_SINCRONIZACAO[status] : "neutro";
}

const TOM_EMPRESA: Record<string, Tom> = { ok: "bom", atencao: "aviso", critico: "critico" };

export function tomDaEmpresa(status: string): Tom {
  return TOM_EMPRESA[status] ?? "neutro";
}

export const ROTULO_EMPRESA: Record<string, string> = {
  ok: "OK",
  atencao: "Atenção",
  critico: "Crítico",
};

export const ROTULO_SINCRONIZACAO: Record<string, string> = {
  sucesso: "Sucesso",
  parcial: "Parcial",
  erro: "Erro",
  em_andamento: "Em andamento",
};


export function opcoesDeStatus(vistos: Array<string | null | undefined>, aplicado = ""): string[] {
  const extras = new Set<string>();
  for (const s of vistos) {
    const n = normalizarStatus(s);
    if (n !== SEM_STATUS) extras.add(n);
  }
  if (aplicado.trim()) extras.add(aplicado.trim().toUpperCase());
  for (const s of STATUS_CONHECIDOS) extras.delete(s);
  return [...STATUS_CONHECIDOS, ...[...extras].sort()];
}
