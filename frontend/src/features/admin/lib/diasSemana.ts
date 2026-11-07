
export const DIAS_SEMANA = [
  { dia: 1, curto: "Seg", nome: "segunda" },
  { dia: 2, curto: "Ter", nome: "terça" },
  { dia: 3, curto: "Qua", nome: "quarta" },
  { dia: 4, curto: "Qui", nome: "quinta" },
  { dia: 5, curto: "Sex", nome: "sexta" },
  { dia: 6, curto: "Sáb", nome: "sábado" },
  { dia: 7, curto: "Dom", nome: "domingo" },
];

export const TODOS_OS_DIAS = DIAS_SEMANA.map((d) => d.dia);


export function descreverDias(dias: number[]): string {
  const ordenados = [...dias].sort((a, b) => a - b);
  if (ordenados.length === 7) return "todo dia";
  if (ordenados.join() === "1,2,3,4,5") return "de segunda a sexta";
  if (ordenados.join() === "1,2,3,4,5,6") return "de segunda a sábado";
  const nomes = ordenados.map((d) => DIAS_SEMANA[d - 1]?.curto.toLowerCase() ?? String(d));
  return nomes.length > 1 ? `${nomes.slice(0, -1).join(", ")} e ${nomes.at(-1)}` : (nomes[0] ?? "");
}
