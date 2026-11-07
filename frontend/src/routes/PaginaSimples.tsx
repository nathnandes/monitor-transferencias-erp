import type { ReactNode } from "react";

import { AppShell } from "../components/layout/AppShell";
import { Header } from "../components/layout/Header";

interface PaginaSimplesProps {
  titulo: string;
  subtitulo?: string;
  children: ReactNode;
}


export function PaginaSimples({ titulo, subtitulo, children }: PaginaSimplesProps) {
  return (
    <AppShell header={<Header titulo={titulo} subtitulo={subtitulo} />}>
      <div className="rounded-painel border border-borda bg-superficie shadow-painel">{children}</div>
    </AppShell>
  );
}
