import type { ReactNode } from "react";

import { MARCA } from "../../lib/marca";

export const NOME_EMPRESA = MARCA.completa;
export const NOME_SISTEMA = "ERP Automation";
export const IDENTIFICACAO_LOCAL = "Acesso local · usuários cadastrados neste sistema";

interface AuthLayoutProps {
  titulo: string;
  descricao?: ReactNode;
  children: ReactNode;
}


export function AuthLayout({ titulo, descricao, children }: AuthLayoutProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-superficie lg:flex-row">
      <aside className="tema-escuro relative flex shrink-0 flex-col overflow-hidden bg-plano px-6 py-6 text-texto lg:w-[44%] lg:max-w-2xl lg:justify-between lg:px-14 lg:py-12">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-acento"
        />
        <div className="relative flex items-center gap-4 lg:flex-col lg:items-start lg:gap-10">
          <div className="leading-tight">
            <p className="marca-apoio text-[11px] text-acento-texto lg:text-xs">{NOME_SISTEMA}</p>
            <p className="mt-2 hidden max-w-md font-display text-3xl font-bold leading-tight tracking-tight text-balance lg:block">
              Painel operacional das lojas
            </p>
            <p className="mt-1 text-xs text-texto-mudo lg:mt-3 lg:max-w-sm lg:text-sm lg:leading-relaxed">
              Transferências, vendas, estoque e alertas, lidos do ERP.
            </p>
          </div>
        </div>
        <p className="relative mt-10 hidden text-xs text-texto-mudo lg:block">{NOME_EMPRESA}</p>
      </aside>

      <div className="flex flex-1 items-center justify-center px-5 py-10 sm:px-10">
        <main className="flex w-full max-w-sm flex-col gap-8">
          <section aria-labelledby="titulo-auth">
            <p className="text-xs font-medium text-texto-mudo">{IDENTIFICACAO_LOCAL}</p>
            <h1 id="titulo-auth" className="mt-3 text-2xl font-bold text-texto">
              {titulo}
            </h1>
            {descricao && <div className="mt-2 text-sm text-texto-2">{descricao}</div>}
            <div className="mt-8">{children}</div>
          </section>

          <p className="border-t border-borda pt-5 text-xs leading-relaxed text-texto-mudo">
            Não tem acesso? Peça ao administrador do sistema.
          </p>
        </main>
      </div>
    </div>
  );
}


export function CampoAuth({ id, rotulo, children }: { id: string; rotulo: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-texto-2">
        {rotulo}
      </label>
      {children}
    </div>
  );
}


export function AlertaAuth({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="rounded-md border border-critico/40 bg-critico/[0.06] px-3 py-2.5 text-sm text-critico-texto">
      {children}
    </div>
  );
}
