

import type { CanalVenda, ParamsVendas, PontoVendas, ResumoVendas } from "../../../types/api";
import type { EstadoFiltroGlobal } from "../../../hooks/useFiltroGlobal";
import { ehDataValida } from "../../../lib/datas";
import { somarDias } from "../../../lib/periodo";
import { calcularVariacao, type Sentido, type Variacao } from "../../../lib/variacao";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = [
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

export const CANAIS: { valor: CanalVenda; rotulo: string }[] = [
  { valor: "balcao", rotulo: "Balcão" },
  { valor: "televendas", rotulo: "Televendas" },
  { valor: "faturamento", rotulo: "Faturamento" },
];

export function ehCanal(valor: string | null): valor is CanalVenda {
  return CANAIS.some((c) => c.valor === valor);
}


export function paraNumero(valor: string | null | undefined): number {
  const n = Number(valor);
  return Number.isFinite(n) ? n : 0;
}

export interface PontoGrafico {
  chave: string;

  rotulo: string;

  rotuloCompleto: string;
  faturamento: number;
  notas: number;
  quantidade: number;

  devolucoes: number | null;

  liquido: number;
}

function rotulos(chave: string, granularidade: "dia" | "mes", variosAnos: boolean): [string, string] {
  const [ano = "", mes = "01", dia] = chave.split("-");
  const indice = Number(mes) - 1;
  if (granularidade === "mes") {
    const curto = MESES[indice] ?? mes;
    return [variosAnos ? `${curto}/${ano.slice(2)}` : curto, `${MESES_LONGOS[indice] ?? mes} de ${ano}`];
  }
  return [`${dia}/${mes}`, `${dia}/${mes}/${ano}`];
}

export function prepararSerie(serie: PontoVendas[], granularidade: "dia" | "mes"): PontoGrafico[] {
  const anos = new Set(serie.map((p) => p.chave.slice(0, 4)));
  return serie.map((p) => {
    const [rotulo, rotuloCompleto] = rotulos(p.chave, granularidade, anos.size > 1);
    return {
      chave: p.chave,
      rotulo,
      rotuloCompleto,
      faturamento: paraNumero(p.faturamento),
      notas: p.notas,
      quantidade: paraNumero(p.quantidade),
      devolucoes: p.devolucoes === null || p.devolucoes === undefined ? null : paraNumero(p.devolucoes),
      liquido: paraNumero(p.faturamento) - paraNumero(p.devolucoes),
    };
  });
}


export function nomeCategoria(categoria: string): string {
  const texto = categoria.trim().toLowerCase();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

const PARTICULAS = new Set(["da", "das", "de", "do", "dos", "e"]);


export function nomeProprio(nome: string): string {
  return nome
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .map((palavra, i) => (i > 0 && PARTICULAS.has(palavra) ? palavra : palavra.charAt(0).toUpperCase() + palavra.slice(1)))
    .join(" ");
}


export function participacao(valor: number, total: number): number {
  return total > 0 ? (valor / total) * 100 : 0;
}

const PERCENTUAL = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function formatarPercentual(valor: number): string {
  return `${PERCENTUAL.format(valor)}%`;
}


export function paramsDasVendas(
  { filtro, intervalo, comparacao }: Pick<EstadoFiltroGlobal, "filtro" | "intervalo" | "comparacao">,
  canal: CanalVenda | null,
  dias: string[] = [],
): ParamsVendas {
  if (dias.length > 0) {
    return { empresa: filtro.empresa || undefined, canal: canal ?? undefined, dias: dias.join(",") };
  }
  return {
    empresa: filtro.empresa || undefined,
    canal: canal ?? undefined,
    data_inicial: intervalo?.inicio,
    data_final: intervalo?.fim,
    comparar_inicial: comparacao?.inicio,
    comparar_final: comparacao?.fim,
  };
}


export const MAX_DIAS_ESCOLHIDOS = 60;


export const DIAS_DA_SEMANA = [
  { valor: 6, singular: "sábado", plural: "sábados" },
  { valor: 0, singular: "domingo", plural: "domingos" },
  { valor: 1, singular: "segunda", plural: "segundas" },
  { valor: 2, singular: "terça", plural: "terças" },
  { valor: 3, singular: "quarta", plural: "quartas" },
  { valor: 4, singular: "quinta", plural: "quintas" },
  { valor: 5, singular: "sexta", plural: "sextas" },
];

const diaDaSemana = (dia: string) => new Date(`${dia}T00:00:00Z`).getUTCDay();


export function ultimosDiasDaSemana(semana: number, quantidade: number, hoje: string): string[] {
  const recuo = (diaDaSemana(hoje) - semana + 7) % 7;
  const n = Math.min(Math.max(quantidade, 0), MAX_DIAS_ESCOLHIDOS);
  return Array.from({ length: n }, (_, i) => somarDias(hoje, -recuo - 7 * (n - 1 - i)));
}


export function lerDias(texto: string | null): string[] {
  if (!texto) return [];
  const validos = texto.split(",").map((d) => d.trim()).filter(ehDataValida);
  return [...new Set(validos)].sort().slice(-MAX_DIAS_ESCOLHIDOS);
}


export function descreverDias(dias: string[]): string {
  const semanas = new Set(dias.map(diaDaSemana));
  const nome = semanas.size === 1 ? DIAS_DA_SEMANA.find((s) => semanas.has(s.valor)) : undefined;
  if (nome) return `${dias.length} ${dias.length === 1 ? nome.singular : nome.plural}`;
  return `${dias.length} ${dias.length === 1 ? "dia escolhido" : "dias escolhidos"}`;
}


export function variacaoDoTotal(
  resumo: ResumoVendas | null,
  campo: "faturamento" | "faturamento_liquido" | "devolucoes" | "notas" | "ticket_medio" | "quantidade",
  rotulo: string | undefined,
  sentido: Sentido = "subir",
): { valor: Variacao; rotulo: string } | null {
  if (!resumo?.comparacao || !rotulo) return null;
  const atual = resumo.totais[campo];
  const anterior = resumo.comparacao[campo];
  if (atual === null || anterior === null) return null;
  return {
    valor: calcularVariacao(paraNumero(String(atual)), paraNumero(String(anterior)), rotulo, sentido),
    rotulo,
  };
}


export function historicoIncompleto(resumo: ResumoVendas | null): boolean {
  if (!resumo) return false;
  const { desde } = resumo.cobertura;
  if (!desde) return true;
  const inicio = resumo.filtro.data_inicial;
  return Boolean(inicio && inicio < desde);
}
