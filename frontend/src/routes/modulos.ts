import { ArrowLeftRight, Bell, LayoutDashboard, Package, ShieldCheck, ShoppingCart, Wallet, type LucideIcon } from "lucide-react";

import type { Aba, Modulo, Usuario } from "../types/auth";
import { abaLiberada, ehAba, infoAba } from "./abas";

export interface InfoModulo {
  modulo: Modulo;
  rota: string;
  rotulo: string;
  icone: LucideIcon;

  implementado: boolean;

  somenteAdmin?: boolean;
}


export const MODULOS: InfoModulo[] = [
  { modulo: "DASHBOARD", rota: "/dashboard", rotulo: "Dashboard", icone: LayoutDashboard, implementado: true },
  { modulo: "TRANSFERENCIAS", rota: "/transferencias", rotulo: "Transferências", icone: ArrowLeftRight, implementado: true },
  { modulo: "ESTOQUE", rota: "/estoque", rotulo: "Estoque", icone: Package, implementado: true },
  { modulo: "VENDAS", rota: "/vendas", rotulo: "Vendas", icone: ShoppingCart, implementado: true },
  { modulo: "FINANCEIRO", rota: "/financeiro", rotulo: "Financeiro", icone: Wallet, implementado: true },
  { modulo: "ALERTAS", rota: "/alertas", rotulo: "Alertas", icone: Bell, implementado: true },

  {
    modulo: "ADMINISTRACAO",
    rota: "/admin/usuarios",
    rotulo: "Administração",
    icone: ShieldCheck,
    implementado: true,
    somenteAdmin: true,
  },
];

export function podeAcessar(info: InfoModulo, modulos: readonly Modulo[], role: Usuario["role"]): boolean {
  return modulos.includes(info.modulo) && (!info.somenteAdmin || role === "ADMIN");
}

export function modulosPermitidos(modulos: readonly Modulo[], role: Usuario["role"]): InfoModulo[] {
  return MODULOS.filter((m) => podeAcessar(m, modulos, role));
}


export function rotaInicial(
  modulos: readonly Modulo[],
  role: Usuario["role"],
  telaInicial: string | null = null,
  abas: readonly Aba[] | null = null,
): string | null {
  if (telaInicial) {
    if (ehAba(telaInicial)) {
      if (abaLiberada(telaInicial, modulos, abas)) return infoAba(telaInicial).rota;
    } else {
      const info = MODULOS.find((m) => m.modulo === telaInicial);
      if (info && podeAcessar(info, modulos, role)) return info.rota;
    }
  }
  const permitidos = modulosPermitidos(modulos, role);
  return (permitidos.find((m) => m.implementado) ?? permitidos[0])?.rota ?? null;
}
