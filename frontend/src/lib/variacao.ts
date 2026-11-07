

import type { Tom } from "./status";


export type Sentido = "subir" | "descer" | "neutro";

export interface Variacao {

  texto: string;
  tom: Tom;

  descricao: string;
}

const PERCENTUAL = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

export function calcularVariacao(atual: number, anterior: number, rotulo: string, sentido: Sentido): Variacao {
  const vs = `vs. ${rotulo}`;
  if (atual === anterior) {
    return { texto: "= igual", tom: "neutro", descricao: `Igual a ${rotulo} (${anterior}).` };
  }

  const subiu = atual > anterior;
  const tom: Tom = sentido === "neutro" ? "neutro" : subiu === (sentido === "subir") ? "bom" : "critico";
  const seta = subiu ? "▲" : "▼";


  if (anterior === 0) {
    return { texto: `${seta} novo`, tom, descricao: `${atual} contra nenhum ${vs}.` };
  }

  const percentual = Math.abs(((atual - anterior) / anterior) * 100);

  const valor = percentual < 1 ? "< 1" : PERCENTUAL.format(percentual);
  return {
    texto: `${seta} ${valor}%`,
    tom,
    descricao: `${valor}% ${subiu ? "a mais" : "a menos"} que ${rotulo} (${anterior}).`,
  };
}
