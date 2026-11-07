

import { env } from "./env";
import { rotuloDia, rotuloDiaCurto } from "./format";

export type Periodo = "hoje" | "ontem" | "mes" | "tudo" | "personalizado";

export const PERIODOS: { valor: Periodo; rotulo: string }[] = [
  { valor: "hoje", rotulo: "Hoje" },
  { valor: "ontem", rotulo: "Ontem" },
  { valor: "mes", rotulo: "Mês" },
  { valor: "tudo", rotulo: "Tudo" },
  { valor: "personalizado", rotulo: "Personalizado" },
];

export interface Intervalo {
  inicio: string;
  fim: string;
}

export interface Comparacao extends Intervalo {

  rotulo: string;
}

const DIAS_SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const MESES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

function nomeDoMes(indice: number): string {
  return MESES[indice] ?? "";
}

function paraData(dia: string): Date {
  return new Date(`${dia}T00:00:00Z`);
}

function paraDia(data: Date): string {
  return data.toISOString().slice(0, 10);
}

export function somarDias(dia: string, dias: number): string {
  const data = paraData(dia);
  data.setUTCDate(data.getUTCDate() + dias);
  return paraDia(data);
}


export function duracaoEmDias({ inicio, fim }: Intervalo): number {
  return Math.round((paraData(fim).getTime() - paraData(inicio).getTime()) / 86_400_000) + 1;
}

function diaDaSemana(dia: string): number {
  return paraData(dia).getUTCDay();
}


function diaDaSemanaPassado(dia: string): string {
  const indice = diaDaSemana(dia);
  const masculino = indice === 0 || indice === 6;
  return `${DIAS_SEMANA[indice] ?? ""} ${masculino ? "passado" : "passada"}`;
}


export function hojeNoFuso(agora: Date = new Date(), tz = env.timezone): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(
    agora,
  );
}


export function intervaloDoPeriodo(periodo: Periodo, hoje: string, personalizado?: Partial<Intervalo>): Intervalo | null {
  switch (periodo) {
    case "hoje":
      return { inicio: hoje, fim: hoje };
    case "ontem": {
      const ontem = somarDias(hoje, -1);
      return { inicio: ontem, fim: ontem };
    }
    case "mes":
      return { inicio: `${hoje.slice(0, 8)}01`, fim: hoje };
    case "personalizado":
      return personalizado?.inicio && personalizado.fim && personalizado.inicio <= personalizado.fim
        ? { inicio: personalizado.inicio, fim: personalizado.fim }
        : null;
    case "tudo":
      return null;
  }
}


export function comparacaoDoPeriodo(periodo: Periodo, intervalo: Intervalo | null): Comparacao | null {
  if (!intervalo) return null;
  switch (periodo) {
    case "hoje": {
      const dia = somarDias(intervalo.inicio, -7);
      return { inicio: dia, fim: dia, rotulo: diaDaSemanaPassado(intervalo.inicio) };
    }
    case "ontem": {
      const dia = somarDias(intervalo.inicio, -7);
      return { inicio: dia, fim: dia, rotulo: `${DIAS_SEMANA[diaDaSemana(dia)] ?? ""}, ${rotuloDiaCurto(dia)}` };
    }
    case "mes": {
      const ano = Number(intervalo.fim.slice(0, 4));
      const mes = Number(intervalo.fim.slice(5, 7));
      const dia = Number(intervalo.fim.slice(8, 10));

      const ultimoDoAnterior = new Date(Date.UTC(ano, mes - 1, 0));
      const inicio = paraDia(new Date(Date.UTC(ultimoDoAnterior.getUTCFullYear(), ultimoDoAnterior.getUTCMonth(), 1)));
      const fim = paraDia(
        new Date(Date.UTC(ultimoDoAnterior.getUTCFullYear(), ultimoDoAnterior.getUTCMonth(), Math.min(dia, ultimoDoAnterior.getUTCDate()))),
      );
      return { inicio, fim, rotulo: `mesmo período de ${nomeDoMes(ultimoDoAnterior.getUTCMonth())}` };
    }
    case "personalizado": {
      const dias = duracaoEmDias(intervalo);
      return {
        inicio: somarDias(intervalo.inicio, -dias),
        fim: somarDias(intervalo.inicio, -1),
        rotulo: dias === 1 ? "dia anterior" : `${dias} dias anteriores`,
      };
    }
    case "tudo":
      return null;
  }
}


export function descreverPeriodo(periodo: Periodo, intervalo: Intervalo | null): string {
  if (periodo === "hoje") return "Hoje";
  if (periodo === "ontem") return "Ontem";
  if (!intervalo) return "Todo o período";
  if (periodo === "mes") {
    const mes = nomeDoMes(Number(intervalo.fim.slice(5, 7)) - 1);
    return `${mes.charAt(0).toUpperCase()}${mes.slice(1)} até dia ${Number(intervalo.fim.slice(8))}`;
  }
  return intervalo.inicio === intervalo.fim
    ? rotuloDia(intervalo.inicio)
    : `${rotuloDia(intervalo.inicio)} a ${rotuloDia(intervalo.fim)}`;
}
