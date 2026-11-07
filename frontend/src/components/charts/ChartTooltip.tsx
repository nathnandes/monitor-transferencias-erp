import type { ReactNode } from "react";

import { formatarNumero } from "../../lib/format";

interface LinhaTooltip {
  nome: string;
  valor: number;
  cor: string;
}


export interface ItemPayload {
  name?: string | number;
  value?: unknown;
  color?: string;
  fill?: string;
  payload?: unknown;
}

export interface PropsConteudoTooltip {
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<ItemPayload>;
}

export function CaixaTooltip({ titulo, linhas }: { titulo: ReactNode; linhas: LinhaTooltip[] }) {
  return (
    <div className="rounded-lg border border-borda bg-superficie px-3 py-2 text-xs shadow-elevado">
      <p className="mb-1 font-medium text-texto">{titulo}</p>
      {linhas.map((l) => (
        <p key={l.nome} className="flex items-center gap-2 text-texto-2">
          <span aria-hidden className="size-2 rounded-sm" style={{ background: l.cor }} />
          {l.nome}
          <span className="tabular ml-auto pl-3 font-medium text-texto">{formatarNumero(l.valor)}</span>
        </p>
      ))}
    </div>
  );
}


export function criarTooltip(
  titulo: (label: string, dados: unknown) => ReactNode,
  cor: (item: ItemPayload) => string,
) {
  return function ConteudoTooltip({ active, payload, label }: PropsConteudoTooltip) {
    if (!active || !payload?.length) return null;
    return (
      <CaixaTooltip
        titulo={titulo(String(label ?? ""), payload[0]?.payload)}
        linhas={payload.map((p) => ({
          nome: String(p.name ?? ""),
          valor: Number(p.value ?? 0),
          cor: cor(p),
        }))}
      />
    );
  };
}
