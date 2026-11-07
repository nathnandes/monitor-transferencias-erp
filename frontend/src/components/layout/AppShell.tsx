import type { ReactNode } from "react";

import { AvisoSemCoi } from "./AvisoSemCoi";
import { BarraSuperior } from "./BarraSuperior";
import { MARCA } from "../../lib/marca";

interface AppShellProps {

  header: ReactNode;
  children: ReactNode;
}


export function AppShell({ header, children }: AppShellProps) {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-acento focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-black"
      >
        Pular para o conteúdo
      </a>
      <BarraSuperior />
      {header}
      <main id="conteudo" tabIndex={-1} className="flex-1 px-4 py-6 outline-none sm:px-6 sm:py-8">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-secao">
          <AvisoSemCoi />
          {children}
        </div>
      </main>
      <footer className="border-t border-borda bg-superficie px-4 py-4 sm:px-6">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-x-6 gap-y-1 text-xs text-texto-mudo">
          <p>
            <span className="font-semibold text-texto-2">{MARCA.curta}</span> · {MARCA.ramo}
          </p>
          <p>ERP Automation · {MARCA.aviso}</p>
        </div>
      </footer>
    </div>
  );
}
