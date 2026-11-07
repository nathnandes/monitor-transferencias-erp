import { ArrowRight, Eye } from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "../../../components/ui/StatusBadge";
import { formatarDataHora, formatarMoeda, nomeCurtoEmpresa, tempoRelativo } from "../../../lib/format";
import { normalizarStatus, rotuloDoStatus, tomDoStatus } from "../../../lib/status";
import type { EmpresaResumo, Transferencia } from "../../../types/api";

interface TransfersTableProps {
  itens: Transferencia[];

  carregando?: boolean;
  aoAbrir: (id: number) => void;
}

function Empresa({ empresa }: { empresa: EmpresaResumo | null }) {
  if (!empresa) return <span className="font-medium text-critico-texto">Fora das empresas</span>;
  return (
    <span title={empresa.nome} className="whitespace-nowrap">
      <span className="font-semibold text-texto">{empresa.codigo}</span>
      <span className="text-texto-2"> {nomeCurtoEmpresa(empresa.nome)}</span>
    </span>
  );
}


function Situacao({ t }: { t: Transferencia }) {
  const status = normalizarStatus(t.status);
  let quando: string | null = null;
  if (status === "PROCESSADA") quando = `chegou ${formatarDataHora(t.data_processamento)}`;
  else if (status === "PENDENTE" && t.data_criacao) quando = `saiu ${tempoRelativo(t.data_criacao)}`;
  return (
    <div className="flex flex-col items-start gap-1">
      <StatusBadge tom={tomDoStatus(t.status)}>{rotuloDoStatus(t.status)}</StatusBadge>
      {quando && <span className="whitespace-nowrap text-[11px] text-texto-mudo">{quando}</span>}
      {t.situacao_coi === "ERRADO" && <StatusBadge tom="critico">COI errado</StatusBadge>}
    </div>
  );
}


function Rotulo({ children }: { children: ReactNode }) {
  return (
    <span aria-hidden className="mb-0.5 block text-[11px] font-medium uppercase tracking-wide text-texto-mudo md:hidden">
      {children}
    </span>
  );
}

const TH = "px-3 py-2.5 font-semibold";
const TD = "md:px-3 md:py-3";


export function TransfersTable({ itens, carregando = false, aoAbrir }: TransfersTableProps) {
  return (
    <div
      aria-busy={carregando}
      className={`transition-opacity md:max-h-[70vh] md:overflow-auto md:rounded-lg md:border md:border-borda ${carregando ? "opacity-60" : ""}`}
    >
      <table role="table" className="w-full text-left text-sm max-md:block md:min-w-[960px]">
        <caption className="sr-only">Transferências da página atual</caption>
        <thead role="rowgroup" className="max-md:sr-only md:sticky md:top-0 md:z-10">
          <tr role="row" className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo shadow-[inset_0_-1px_0_var(--color-borda)]">
            <th role="columnheader" scope="col" className={TH}>Nota</th>
            <th role="columnheader" scope="col" className={TH}>Saiu em</th>
            <th role="columnheader" scope="col" className={TH}>De → Para</th>
            <th role="columnheader" scope="col" className={TH}>Emitida por</th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Valor</th>
            <th role="columnheader" scope="col" className={`${TH} text-right`}>Itens</th>
            <th role="columnheader" scope="col" className={TH}>Situação</th>
            <th role="columnheader" scope="col" className="px-3 py-2.5"><span className="sr-only">Ações</span></th>
          </tr>
        </thead>
        <tbody role="rowgroup" className="tabular max-md:grid max-md:gap-3">
          {itens.map((t) => (
            <tr
              key={t.id}
              role="row"
              data-sem-coi={t.situacao_coi === "ERRADO" || undefined}
              className={`text-texto-2 transition-colors max-md:grid max-md:grid-cols-2 max-md:gap-x-4 max-md:gap-y-3 max-md:rounded-lg max-md:border max-md:p-3 md:border-b md:border-borda/70 ${
                t.situacao_coi === "ERRADO"
                  ? "bg-critico/10 max-md:border-critico md:shadow-[inset_3px_0_0_var(--color-critico)] md:hover:bg-critico/15"
                  : "max-md:border-borda max-md:bg-superficie-2/40 md:hover:bg-superficie-2"
              }`}
            >
              <td role="cell" className={`whitespace-nowrap max-md:order-first ${TD}`}>
                <Rotulo>Nota</Rotulo>
                <span className="font-semibold text-texto">{t.numero_nota ? `NF ${t.numero_nota}` : t.id_erp}</span>
                <span className="block text-[11px] text-texto-mudo">#{t.id}</span>
              </td>
              <td role="cell" className={`whitespace-nowrap ${TD}`}>
                <Rotulo>Saiu em</Rotulo>
                <span>{formatarDataHora(t.data_criacao)}</span>
              </td>
              <td role="cell" className={`max-md:col-span-2 ${TD}`}>
                <Rotulo>De → Para</Rotulo>
                <span className="flex flex-wrap items-center gap-x-1.5">
                  <Empresa empresa={t.empresa_origem} />
                  <ArrowRight aria-label="para" className="size-3.5 shrink-0 text-texto-mudo" />
                  <Empresa empresa={t.empresa_destino} />
                </span>
              </td>
              <td role="cell" className={TD}>
                <Rotulo>Emitida por</Rotulo>
                {t.usuario_emissao ? <span className="text-texto">{t.usuario_emissao}</span> : <span className="text-texto-mudo">—</span>}
              </td>
              <td role="cell" className={`whitespace-nowrap md:text-right ${TD}`}>
                <Rotulo>Valor</Rotulo>
                <span className="font-medium text-texto">{formatarMoeda(t.valor_total)}</span>
              </td>
              <td role="cell" className={`md:text-right ${TD}`}><Rotulo>Itens</Rotulo><span>{t.quantidade_itens ?? "—"}</span></td>
              <td role="cell" className={`max-md:order-first max-md:justify-self-end ${TD}`}>
                <Rotulo>Situação</Rotulo>
                <Situacao t={t} />
              </td>
              <td role="cell" className={`max-md:col-span-2 md:text-right ${TD}`}>
                <button
                  type="button"
                  onClick={() => aoAbrir(t.id)}
                  aria-label={`Ver detalhes da transferência ${t.numero_nota ?? t.id_erp}`}
                  className="btn btn-sm btn-secundario max-md:w-full"
                >
                  <Eye aria-hidden className="size-3.5" />
                  Ver detalhes
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
