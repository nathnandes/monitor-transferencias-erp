import { lazy, type ComponentType } from "react";

import type { Modulo } from "../types/auth";


const CARGAS = {
  DASHBOARD: () => import("../features/dashboard/DashboardPage").then((m) => ({ default: m.DashboardPage })),
  TRANSFERENCIAS: () =>
    import("../features/transfers/TransferenciasPage").then((m) => ({ default: m.TransferenciasPage })),
  ESTOQUE: () => import("../features/estoque/EstoquePage").then((m) => ({ default: m.EstoquePage })),
  VENDAS: () => import("../features/vendas/VendasPage").then((m) => ({ default: m.VendasPage })),
  FINANCEIRO: () => import("../features/financeiro/FinanceiroPage").then((m) => ({ default: m.FinanceiroPage })),
  ALERTAS: () => import("../features/alertas/AlertasPage").then((m) => ({ default: m.AlertasPage })),
  ADMINISTRACAO: () => import("../features/admin/AdminUsuariosPage").then((m) => ({ default: m.AdminUsuariosPage })),
} satisfies Partial<Record<Modulo, () => Promise<{ default: ComponentType }>>>;

type ModuloComTela = keyof typeof CARGAS;

const emAndamento = new Map<ModuloComTela, Promise<{ default: ComponentType }>>();

function carregar(modulo: ModuloComTela) {
  let promessa = emAndamento.get(modulo);
  if (!promessa) {

    promessa = CARGAS[modulo]().catch((erro: unknown) => {
      emAndamento.delete(modulo);
      throw erro;
    });
    emAndamento.set(modulo, promessa);
  }
  return promessa;
}

export const DashboardPage = lazy(() => carregar("DASHBOARD"));
export const TransferenciasPage = lazy(() => carregar("TRANSFERENCIAS"));
export const EstoquePage = lazy(() => carregar("ESTOQUE"));
export const VendasPage = lazy(() => carregar("VENDAS"));
export const FinanceiroPage = lazy(() => carregar("FINANCEIRO"));
export const AlertasPage = lazy(() => carregar("ALERTAS"));
export const AdminUsuariosPage = lazy(() => carregar("ADMINISTRACAO"));

export const AdminAlertasPage = lazy(() =>
  import("../features/admin/AdminAlertasPage").then((m) => ({ default: m.AdminAlertasPage })),
);


export const AdminHistoricoPage = lazy(() =>
  import("../features/admin/AdminHistoricoPage").then((m) => ({ default: m.AdminHistoricoPage })),
);


export const MetasPage = lazy(() => import("../features/vendas/MetasPage").then((m) => ({ default: m.MetasPage })));


export const ControlePage = lazy(() =>
  import("../features/transfers/ControlePage").then((m) => ({ default: m.ControlePage })),
);


export const TvPage = lazy(() => import("../features/tv/TvPage").then((m) => ({ default: m.TvPage })));


export const VendasTvPage = lazy(() =>
  import("../features/vendas/VendasTvPage").then((m) => ({ default: m.VendasTvPage })),
);


export function precarregarTela(modulo: Modulo) {
  if (modulo in CARGAS) carregar(modulo as ModuloComTela).catch(() => {});
}
