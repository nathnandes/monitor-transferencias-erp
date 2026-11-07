import { LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { LoadingState } from "../ui/LoadingState";
import { Panel } from "../ui/Panel";
import { ALTURA_PADRAO } from "./chartTheme";

interface ChartPanelProps {
  titulo: string;
  subtitulo?: ReactNode;

  acao?: ReactNode;

  carregando: boolean;

  atualizando?: boolean;
  erro: Error | null;
  vazio: boolean;
  mensagemVazio?: string;
  aoTentarNovamente: () => void;

  descricao?: string;
  children: ReactNode;
}


function SeloAtualizando() {
  return (
    <span role="status" className="inline-flex items-center gap-1.5 text-xs text-texto-mudo">
      <LoaderCircle aria-hidden className="size-3.5 animate-spin text-acento-forte" />
      Atualizando
    </span>
  );
}


export function ChartPanel({
  titulo,
  subtitulo,
  acao,
  carregando,
  atualizando = false,
  erro,
  vazio,
  mensagemVazio = "Nenhum registro para exibir.",
  aoTentarNovamente,
  descricao,
  children,
}: ChartPanelProps) {
  const altura = ALTURA_PADRAO;
  let corpo: ReactNode;
  if (erro) {
    corpo = (
      <ErrorState
        titulo={`Falha ao carregar: ${titulo}`}
        erro={erro}
        aoTentarNovamente={aoTentarNovamente}
        className="min-h-[260px] justify-center"
      />
    );
  } else if (carregando) {
    corpo = <LoadingState altura={altura} />;
  } else if (vazio) {
    corpo = (
      <div style={{ minHeight: altura }} className="grid place-items-center rounded-lg border border-dashed border-borda">
        <EmptyState titulo="Sem dados para exibir" descricao={mensagemVazio} />
      </div>
    );
  } else {
    corpo = (
      <figure aria-label={titulo} aria-busy={atualizando} className={`transition-opacity ${atualizando ? "opacity-60" : ""}`}>
        {descricao && <figcaption className="sr-only">{descricao}</figcaption>}
        {children}
      </figure>
    );
  }

  const mostrarSelo = atualizando && !carregando && !erro;
  return (
    <Panel
      titulo={titulo}
      subtitulo={subtitulo}
      acao={
        (mostrarSelo || acao) && (
          <>
            {mostrarSelo && <SeloAtualizando />}
            {acao}
          </>
        )
      }
    >
      {corpo}
    </Panel>
  );
}
