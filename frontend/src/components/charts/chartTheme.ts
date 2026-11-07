

import { COR_TOM, tomDaSeveridade, tomDoStatus } from "../../lib/status";

export const COR_SERIE_1 = "#1f2933";
export const COR_SERIE_2 = "#2f6fde";

export const COR_SUPERFICIE = "#ffffff";
export const COR_GRADE = "#eceef2";
export const COR_EIXO = "#cfd3da";
export const COR_TICK = "#686e78";
export const COR_TICK_FORTE = "#474c55";
export const COR_ROTULO = "#1c1f24";

export const TICK = { fill: COR_TICK, fontSize: 12 };
export const TICK_CATEGORIA = { fill: COR_TICK_FORTE, fontSize: 12 };
export const ALTURA_PADRAO = 260;


export const CURSOR_BARRA = { fill: "rgba(16,24,40,0.04)" };


export function corDoStatus(status: string): string {
  return COR_TOM[tomDoStatus(status)];
}


export function corDaSeveridade(severidade: string): string {
  return COR_TOM[tomDaSeveridade(severidade)];
}
