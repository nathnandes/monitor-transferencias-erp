

import { COR_TOM } from "../../../lib/status";
import type { GranularidadeIndicadores, PontoIndicadores } from "../../../types/api";
import { COR_SERIE_1, COR_SERIE_2 } from "../../../components/charts/chartTheme";

export type CampoIndicador = Exclude<keyof PontoIndicadores, "chave">;

export interface DefinicaoIndicador {
  campo: CampoIndicador;
  titulo: string;
  dica: string;
  cor: string;
  formatar: (valor: number) => string;
}


const UMA_CASA = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const numero = (v: number) => UMA_CASA.format(v);
const percentual = (v: number) => `${UMA_CASA.format(v)}%`;
const horas = (v: number) => `${UMA_CASA.format(v)} h`;


export const INDICADORES: DefinicaoIndicador[] = [
  {
    campo: "a_receber",
    titulo: "A receber",
    dica: "Notas de transferência para a empresa ainda sem entrada (pendentes agora), pela data da saída.",
    cor: COR_TOM.aviso,
    formatar: numero,
  },
  {
    campo: "recebidas",
    titulo: "Recebidas",
    dica: "Entradas de transferência feitas pela empresa, pela data da entrada.",
    cor: COR_SERIE_2,
    formatar: numero,
  },
  {
    campo: "taxa_entrada",
    titulo: "Taxa de entrada",
    dica: "Das notas para a empresa no período, quantas já tiveram entrada.",
    cor: COR_TOM.bom,
    formatar: percentual,
  },
  {
    campo: "tempo_medio_entrada_horas",
    titulo: "Tempo médio de entrada",
    dica: "Horas, em média, entre a saída na origem e a entrada na empresa.",
    cor: COR_SERIE_2,
    formatar: horas,
  },
  { campo: "enviadas", titulo: "Enviadas", dica: "Notas de transferência emitidas pela empresa.", cor: COR_SERIE_1, formatar: numero },
  { campo: "itens_enviados", titulo: "Itens enviados", dica: "Soma dos itens das transferências enviadas.", cor: COR_SERIE_1, formatar: numero },
  {
    campo: "aguardando_destino",
    titulo: "Aguardando o destino",
    dica: "Das enviadas no período, quantas o destino ainda não deu entrada.",
    cor: COR_TOM.aviso,
    formatar: numero,
  },
  {
    campo: "coi_errado",
    titulo: "COI errado",
    dica: "Transferências da empresa (enviadas ou recebidas) com nota sem COI no ERP.",
    cor: COR_TOM.critico,
    formatar: numero,
  },
];

const MESES_CURTOS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];


export function rotuloBalde(chave: string, granularidade: GranularidadeIndicadores): string {
  if (granularidade === "hora") return `${Number(chave.slice(11, 13))}h`;
  if (granularidade === "dia") return `${chave.slice(8, 10)}/${chave.slice(5, 7)}`;
  return `${MESES_CURTOS[Number(chave.slice(5, 7)) - 1] ?? ""}/${chave.slice(2, 4)}`;
}


export function rotuloBaldeCompleto(chave: string, granularidade: GranularidadeIndicadores): string {
  const dia = `${chave.slice(8, 10)}/${chave.slice(5, 7)}/${chave.slice(0, 4)}`;
  if (granularidade === "hora") return `${dia} ${Number(chave.slice(11, 13))}h`;
  if (granularidade === "dia") return dia;
  return `${MESES_CURTOS[Number(chave.slice(5, 7)) - 1] ?? ""}/${chave.slice(0, 4)}`;
}

export interface PontoCard {
  chave: string;
  rotulo: string;
  rotuloCompleto: string;
  valor: number | null;
  media: number | null;
}


export function pontosDoCard(
  serie: PontoIndicadores[],
  campo: CampoIndicador,
  granularidade: GranularidadeIndicadores,
): PontoCard[] {
  const valores = serie.map((p) => p[campo]);
  const comValor = valores.filter((v): v is number => v !== null);
  const media = comValor.length ? comValor.reduce((a, b) => a + b, 0) / comValor.length : null;
  return serie.map((p, i) => ({
    chave: p.chave,
    rotulo: rotuloBalde(p.chave, granularidade),
    rotuloCompleto: rotuloBaldeCompleto(p.chave, granularidade),
    valor: valores[i] ?? null,
    media,
  }));
}


export function semMovimento(totais: PontoIndicadores): boolean {
  return totais.enviadas === 0 && totais.recebidas === 0 && totais.a_receber === 0;
}
