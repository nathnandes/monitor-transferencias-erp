

import { env } from "./env";
import type { TotaisTransferencias, Transferencia } from "../types/api";
import { chaveDia, rotuloDia, rotuloDiaCurto } from "./format";
import { SEVERIDADES } from "./status";

export interface ContagemStatus {
  status: string;
  total: number;
}


export const STATUS_OUTROS = "OUTROS";


export function statusDoResumo(t: TotaisTransferencias): ContagemStatus[] {
  if (t.total === 0) return [];
  const contados: ContagemStatus[] = [
    { status: "PROCESSADA", total: t.processadas },
    { status: "PENDENTE", total: t.pendentes },
    { status: "ERRO", total: t.com_erro },
  ];
  const outros = t.total - t.processadas - t.pendentes - t.com_erro;
  return outros > 0 ? [...contados, { status: STATUS_OUTROS, total: outros }] : contados;
}

export interface ContagemEmpresa {
  codigo: string;
  nome: string;

  saidas: number;

  entradas: number;
}


export function contarPorEmpresa(itens: Transferencia[]): ContagemEmpresa[] {
  const mapa = new Map<string, ContagemEmpresa>();
  const obter = (codigo: string, nome: string) => {
    let atual = mapa.get(codigo);
    if (!atual) {
      atual = { codigo, nome, saidas: 0, entradas: 0 };
      mapa.set(codigo, atual);
    }
    return atual;
  };
  for (const t of itens) {
    obter(t.empresa_origem.codigo, t.empresa_origem.nome).saidas++;
    if (t.empresa_destino) obter(t.empresa_destino.codigo, t.empresa_destino.nome).entradas++;
  }
  return [...mapa.values()].sort((a, b) => a.codigo.localeCompare(b.codigo));
}

export interface ContagemDia {

  dia: string;
  total: number;
}


export function contarPorDia(itens: Transferencia[], tz = env.timezone): ContagemDia[] {
  const mapa = new Map<string, number>();
  for (const t of itens) {
    if (!t.data_criacao) continue;
    const dia = chaveDia(t.data_criacao, tz);
    mapa.set(dia, (mapa.get(dia) ?? 0) + 1);
  }
  if (mapa.size === 0) return [];

  const dias = [...mapa.keys()].sort();
  const ultimo = dias[dias.length - 1]!;
  const resultado: ContagemDia[] = [];
  for (let dia = dias[0]!; dia <= ultimo; dia = somarDias(dia, 1)) {
    resultado.push({ dia, total: mapa.get(dia) ?? 0 });
  }
  return resultado;
}

export type Granularidade = "dia" | "semana";


export interface PontoSerie {

  chave: string;

  rotulo: string;

  rotuloCompleto: string;
  total: number;
}

export function serieDiaria(dias: ContagemDia[]): PontoSerie[] {
  return dias.map((d) => ({
    chave: d.dia,
    rotulo: rotuloDiaCurto(d.dia),
    rotuloCompleto: rotuloDia(d.dia),
    total: d.total,
  }));
}


function somarDias(chave: string, n: number): string {
  const data = new Date(`${chave}T12:00:00Z`);
  data.setUTCDate(data.getUTCDate() + n);
  return data.toISOString().slice(0, 10);
}


export function inicioDaSemana(chave: string): string {
  const diaSemana = new Date(`${chave}T12:00:00Z`).getUTCDay();
  return somarDias(chave, -((diaSemana + 6) % 7));
}


export function agruparPorSemana(dias: ContagemDia[]): PontoSerie[] {
  const mapa = new Map<string, number>();
  for (const d of dias) {
    const semana = inicioDaSemana(d.dia);
    mapa.set(semana, (mapa.get(semana) ?? 0) + d.total);
  }
  return [...mapa.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([inicio, total]) => ({
      chave: inicio,
      rotulo: rotuloDiaCurto(inicio),
      rotuloCompleto: `Semana de ${rotuloDia(inicio)} a ${rotuloDia(somarDias(inicio, 6))}`,
      total,
    }));
}

export function serieTemporal(dias: ContagemDia[], granularidade: Granularidade): PontoSerie[] {
  return granularidade === "semana" ? agruparPorSemana(dias) : serieDiaria(dias);
}

export interface ContagemSeveridade {
  severidade: string;
  total: number;
}


export function ordenarSeveridades(porSeveridade: Record<string, number>): ContagemSeveridade[] {
  const chaves = Object.keys(porSeveridade);
  const conhecidas = SEVERIDADES.filter((s) => chaves.includes(s));
  const extras = chaves.filter((s) => !(SEVERIDADES as readonly string[]).includes(s)).sort();
  return [...conhecidas, ...extras].map((severidade) => ({
    severidade,
    total: porSeveridade[severidade] ?? 0,
  }));
}


export function ehDadoSimulado(idErp: string | null | undefined): boolean {
  return Boolean(idErp?.startsWith("DEMO-"));
}
