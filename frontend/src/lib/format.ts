

import { env } from "./env";
import type { DataISO, Decimal } from "../types/api";

const NAO_INFORMADO = "—";

function formatador(opcoes: Intl.DateTimeFormatOptions, tz = env.timezone) {
  return new Intl.DateTimeFormat("pt-BR", { timeZone: tz, ...opcoes });
}

export function formatarDataHora(valor: DataISO | null | undefined, tz = env.timezone): string {
  if (!valor) return NAO_INFORMADO;
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return NAO_INFORMADO;
  return formatador(
    { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" },
    tz,
  ).format(data);
}


export function chaveDia(valor: DataISO, tz = env.timezone): string {

  return new Intl.DateTimeFormat("en-CA", {
    timeZone: tz,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(valor));
}


export function rotuloDiaCurto(chave: string): string {
  const [, mes, dia] = chave.split("-");
  return `${dia}/${mes}`;
}


export function rotuloDia(chave: string): string {
  const [ano, mes, dia] = chave.split("-");
  return `${dia}/${mes}/${ano}`;
}


export function tempoRelativo(valor: DataISO | null | undefined, agora: Date = new Date()): string {
  if (!valor) return NAO_INFORMADO;
  const diffMs = agora.getTime() - new Date(valor).getTime();
  if (Number.isNaN(diffMs)) return NAO_INFORMADO;
  const minutos = Math.round(diffMs / 60_000);
  if (minutos < 1) return "agora há pouco";
  if (minutos < 60) return `há ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `há ${horas} h`;
  const dias = Math.round(horas / 24);
  return `há ${dias} ${dias === 1 ? "dia" : "dias"}`;
}


export function formatarQuantidade(valor: Decimal | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return NAO_INFORMADO;
  const texto = String(valor).trim();
  const correspondencia = /^(-?)(\d+)(?:\.(\d+))?$/.exec(texto);
  if (!correspondencia) return texto;
  const [, sinal = "", inteiro = "0", fracao = ""] = correspondencia;
  const inteiroFormatado = inteiro.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const fracaoLimpa = fracao.replace(/0+$/, "");
  return `${sinal}${inteiroFormatado}${fracaoLimpa ? `,${fracaoLimpa}` : ""}`;
}


export function formatarMoeda(valor: Decimal | null | undefined): string {
  if (valor === null || valor === undefined || valor === "") return NAO_INFORMADO;
  const texto = String(valor).trim();
  const correspondencia = /^(-?)(\d+)(?:\.(\d+))?$/.exec(texto);
  if (!correspondencia) return texto;
  const [, sinal = "", inteiro = "0", fracao = ""] = correspondencia;
  const casas = fracao.padEnd(3, "0");
  let centavos = BigInt(inteiro + casas.slice(0, 2));
  if (Number(casas[2]) >= 5) centavos += 1n;
  const reais = (centavos / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const resto = (centavos % 100n).toString().padStart(2, "0");
  return `${sinal && centavos > 0n ? "-" : ""}R$ ${reais},${resto}`;
}

export function formatarNumero(valor: number): string {
  return new Intl.NumberFormat("pt-BR").format(valor);
}


export function formatarHora(data: Date, tz = env.timezone): string {
  return formatador({ hour: "2-digit", minute: "2-digit", second: "2-digit" }, tz).format(data);
}


export function formatarHoraMinuto(data: Date, tz = env.timezone): string {
  return formatador({ hour: "2-digit", minute: "2-digit" }, tz).format(data);
}

const COMPACTO = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const COMPACTO_INTEIRO = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });


export function formatarMoedaCurta(valor: number): string {
  const absoluto = Math.abs(valor);
  const sinal = valor < 0 ? "-" : "";
  if (absoluto >= 1_000_000) return `${sinal}R$ ${COMPACTO.format(absoluto / 1_000_000)} mi`;
  if (absoluto >= 1_000) return `${sinal}R$ ${COMPACTO_INTEIRO.format(absoluto / 1_000)} mil`;
  return `${sinal}R$ ${COMPACTO_INTEIRO.format(absoluto)}`;
}


export function formatarMoedaNumero(valor: number): string {
  return Number.isFinite(valor) ? formatarMoeda(valor.toFixed(3)) : formatarMoeda(null);
}


export function formatarNumeroCurto(valor: number): string {
  const absoluto = Math.abs(valor);
  const sinal = valor < 0 ? "-" : "";
  const umaCasa = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  if (absoluto >= 1_000_000) return `${sinal}${umaCasa.format(absoluto / 1_000_000)} mi`;
  if (absoluto >= 10_000) return `${sinal}${umaCasa.format(absoluto / 1_000)} mil`;
  return `${sinal}${COMPACTO_INTEIRO.format(absoluto)}`;
}


export function nomeCurtoEmpresa(nome: string): string {
  const curto = nome.replace(/^rede\s+exemplo\s*/i, "").trim();
  return curto || nome;
}


export function formatarCnpj(cnpj: string): string {
  if (cnpj.length !== 14) return cnpj;
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`;
}
