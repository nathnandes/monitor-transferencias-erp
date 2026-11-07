

export type CelulaCsv = string | number | null | undefined;


export function celulaCsv(valor: CelulaCsv): string {
  if (valor === null || valor === undefined) return "";
  let texto = String(valor);
  if (typeof valor === "number" || /^-?\d+(\.\d+)?$/.test(texto)) {
    texto = texto.includes(".") ? texto.replace(/0+$/, "").replace(/\.$/, "").replace(".", ",") : texto;
  }
  return /[;"\r\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

export function montarCsv(cabecalho: string[], linhas: CelulaCsv[][]): string {
  return "﻿" + [cabecalho, ...linhas].map((l) => l.map(celulaCsv).join(";")).join("\r\n") + "\r\n";
}

export function baixarCsv(nome: string, cabecalho: string[], linhas: CelulaCsv[][]): void {
  const url = URL.createObjectURL(new Blob([montarCsv(cabecalho, linhas)], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${nome}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
