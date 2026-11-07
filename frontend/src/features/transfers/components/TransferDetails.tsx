import { ArrowRight, Filter, SearchX, Siren, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Modal } from "../../../components/ui/Modal";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { subtrairDecimais } from "../../../lib/decimal";
import { formatarDataHora, formatarMoeda, formatarQuantidade } from "../../../lib/format";
import { ROTULO_SITUACAO_COI, TOM_SITUACAO_COI } from "../../../lib/status";
import { ApiError } from "../../../services/apiClient";
import { getTransferencia } from "../../../services/transferenciasService";
import type { EmpresaResumo, TransferenciaDetalhe, TransferenciaItem } from "../../../types/api";
import { PipelineTransferencia } from "./PipelineTransferencia";
import { TransferStatusBadge } from "./TransferStatusBadge";
import { TratativasPanel } from "./TratativasPanel";

interface TransferDetailsProps {

  id: number | null;
  aoFechar: () => void;
}


export function TransferDetails({ id, aoFechar }: TransferDetailsProps) {
  return (
    <Modal aberto={id !== null} titulo={id !== null ? `Transferência #${id}` : ""} aoFechar={aoFechar}>
      {id !== null && <ConteudoDetalhe id={id} aoFechar={aoFechar} />}
    </Modal>
  );
}

function ConteudoDetalhe({ id, aoFechar }: { id: number; aoFechar: () => void }) {
  const { data, error, loading, recarregar } = useAsync((s) => getTransferencia(id, s), [id]);

  if (error instanceof ApiError && error.status === 404) {
    return (
      <EmptyState
        icone={SearchX}
        titulo={`Transferência #${id} não encontrada`}
        descricao="Ela não existe no banco consultado. O link pode estar desatualizado ou os dados simulados foram recriados."
        acao={
          <button type="button" onClick={aoFechar} className="btn btn-sm btn-secundario">
            Voltar para a lista
          </button>
        }
      />
    );
  }
  if (error) return <ErrorState erro={error} aoTentarNovamente={recarregar} />;
  if (loading || !data) return <LoadingState rotulo="Carregando detalhes..." />;
  return (
    <div className="flex flex-col gap-5">
      <TransferDetailView transferencia={data} />
      <TratativasPanel id={data.id} />
    </div>
  );
}

function Campo({ rotulo, children }: { rotulo: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-texto-mudo">{rotulo}</dt>
      <dd className="mt-0.5 text-sm text-texto">{children}</dd>
    </div>
  );
}

function CartaoEmpresa({ papel, empresa }: { papel: string; empresa: EmpresaResumo | null }) {
  return (
    <div className="flex-1 rounded-lg border border-borda bg-superficie p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-texto-mudo">{papel}</p>
      {empresa ? (
        <p className="mt-1 text-sm font-semibold text-texto">
          {empresa.codigo} <span className="font-normal text-texto-2">— {empresa.nome}</span>
        </p>
      ) : (
        <p className="mt-1 text-sm font-semibold text-critico-texto">Não é uma das empresas</p>
      )}
    </div>
  );
}


function RotuloItem({ children }: { children: ReactNode }) {
  return (
    <span aria-hidden className="block text-[11px] font-medium uppercase tracking-wide text-texto-mudo md:hidden">
      {children}
    </span>
  );
}


function diferenca(item: TransferenciaItem): string | null {
  if (!item.divergente || item.quantidade_processada === null || item.quantidade_solicitada === null) return null;
  const d = subtrairDecimais(item.quantidade_processada, item.quantidade_solicitada);
  if (d === null) return null;
  const formatada = formatarQuantidade(d.replace(/^-/, ""));
  return d.startsWith("-") ? `−${formatada}` : `+${formatada}`;
}

const CELULA = "md:px-3 md:py-2.5";


export function TransferDetailView({ transferencia: t }: { transferencia: TransferenciaDetalhe }) {
  const divergentes = t.itens.filter((i) => i.divergente).length;
  const [soDivergentes, setSoDivergentes] = useState(false);
  const itens = soDivergentes ? t.itens.filter((i) => i.divergente) : t.itens;

  return (
    <div className="flex flex-col gap-5">
      {t.situacao_coi === "ERRADO" && (
        <div role="alert" className="flex items-start gap-3 rounded-lg border-2 border-critico bg-critico/15 p-3 text-sm text-texto">
          <Siren aria-hidden className="size-6 shrink-0 text-critico-texto" />
          <div>
            <strong className="block uppercase tracking-wide text-critico-texto">Transferência com COI errado</strong>
            <ul className="mt-1 list-disc pl-4">
              {t.problemas_coi.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
            <p className="mt-1">Confira a operação no ERP e corrija a nota.</p>
          </div>
        </div>
      )}

      <section aria-label="Pipeline" className="rounded-lg border border-borda bg-superficie p-4">
        <h3 className="mb-4 text-sm font-semibold text-texto">Do início ao fim</h3>
        <PipelineTransferencia etapas={t.etapas} />
      </section>

      <section aria-label="Dados da transferência" className="rounded-lg border border-borda bg-superficie p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <TransferStatusBadge status={t.status} />
          <StatusBadge tom={TOM_SITUACAO_COI[t.situacao_coi]}>{ROTULO_SITUACAO_COI[t.situacao_coi]}</StatusBadge>
          {divergentes > 0 && (
            <StatusBadge tom="serio">
              {divergentes} {divergentes === 1 ? "item divergente" : "itens divergentes"}
            </StatusBadge>
          )}
        </div>
        <dl className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2">
          <Campo rotulo="Nota de saída">{t.numero_nota ?? "—"}</Campo>
          <Campo rotulo="ID no ERP"><span className="font-mono text-xs">{t.id_erp}</span></Campo>
          <Campo rotulo="COI de saída">
            <span className="font-mono text-xs">{t.coi ?? "—"}</span>
          </Campo>
          <Campo rotulo="COI de entrada">
            {t.coi_entrada ? (
              <span className="font-mono text-xs">{t.coi_entrada}</span>
            ) : (
              <span className="text-texto-mudo">Entrada ainda não registrada</span>
            )}
          </Campo>
          <Campo rotulo="Quantidade de itens">{t.quantidade_itens ?? "—"}</Campo>
          <Campo rotulo="Valor da nota">{t.valor_total ? formatarMoeda(t.valor_total) : "—"}</Campo>
          <Campo rotulo="Emitida por">{t.usuario_emissao ?? "—"}</Campo>
          <Campo rotulo="Saída emitida em">{formatarDataHora(t.data_criacao)}</Campo>
          <Campo rotulo="Entrada no destino em">{formatarDataHora(t.data_processamento)}</Campo>
          <Campo rotulo="Registrada no sistema">{formatarDataHora(t.created_at)}</Campo>
          <Campo rotulo="Atualizada no sistema">{formatarDataHora(t.updated_at)}</Campo>
        </dl>
      </section>

      <section aria-label="Origem e destino" className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
        <CartaoEmpresa papel="Origem" empresa={t.empresa_origem} />
        <ArrowRight aria-hidden className="size-5 shrink-0 rotate-90 self-center text-texto-mudo sm:rotate-0" />
        <CartaoEmpresa papel="Destino" empresa={t.empresa_destino} />
      </section>

      <section aria-label="Itens">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-texto">Itens ({t.itens.length})</h3>
          {divergentes > 0 && divergentes < t.itens.length && (
            <button
              type="button"
              aria-pressed={soDivergentes}
              onClick={() => setSoDivergentes((v) => !v)}
              className="btn btn-sm btn-secundario aria-pressed:border-serio aria-pressed:text-serio-texto"
            >
              <Filter aria-hidden className="size-3.5" />
              Somente divergentes
            </button>
          )}
        </div>
        {divergentes > 0 && (
          <p className="mb-2 flex items-center gap-1.5 text-xs text-serio-texto">
            <TriangleAlert aria-hidden className="size-3.5" />
            Quantidade processada diferente da solicitada em {divergentes}{" "}
            {divergentes === 1 ? "item" : "itens"}.
          </p>
        )}
        {t.itens.length === 0 ? (
          <EmptyState titulo="Transferência sem itens registrados" />
        ) : (
          <div className="md:rounded-lg md:border md:border-borda">
            <table role="table" className="w-full text-left text-sm max-md:block">
              <caption className="sr-only">
                Itens da transferência {t.id_erp}
                {soDivergentes ? " (somente divergentes)" : ""}
              </caption>
              {/* -top-5 compensa o padding do corpo do modal, que é o contêiner de rolagem. */}
              <thead role="rowgroup" className="text-xs uppercase tracking-wide text-texto-mudo max-md:sr-only md:sticky md:-top-5 md:z-10">
                <tr role="row" className="bg-superficie-2 shadow-[inset_0_-1px_0_var(--color-borda)]">
                  <th role="columnheader" scope="col" className="px-3 py-2 font-semibold">Produto</th>
                  <th role="columnheader" scope="col" className="px-3 py-2 text-right font-semibold">Solicitada</th>
                  <th role="columnheader" scope="col" className="px-3 py-2 text-right font-semibold">Processada</th>
                  <th role="columnheader" scope="col" className="px-3 py-2 text-right font-semibold">Diferença</th>
                  <th role="columnheader" scope="col" className="px-3 py-2 text-right font-semibold">Valor</th>
                  <th role="columnheader" scope="col" className="px-3 py-2 font-semibold">Situação</th>
                </tr>
              </thead>
              <tbody role="rowgroup" className="tabular max-md:grid max-md:gap-2">
                {itens.map((item) => (
                  <tr
                    key={item.id}
                    role="row"
                    data-divergente={item.divergente || undefined}
                    className={`max-md:grid max-md:grid-cols-3 max-md:gap-x-3 max-md:gap-y-2 max-md:rounded-lg max-md:border max-md:p-3 md:border-t md:border-borda ${
                      item.divergente ? "bg-serio/10 max-md:border-serio/50" : "max-md:border-borda max-md:bg-superficie"
                    }`}
                  >
                    <td role="cell" className={`max-md:col-span-2 ${CELULA} ${item.divergente ? "md:border-l-2 md:border-l-serio" : ""}`}>
                      <p className="text-texto">{item.descricao_produto ?? "Sem descrição"}</p>
                      <p className="text-[11px] text-texto-mudo">
                        {item.codigo_produto ?? "—"} · {item.id_produto_erp}
                        {item.cfop_saida && ` · CFOP ${item.cfop_saida}${item.cfop_entrada ? ` → ${item.cfop_entrada}` : ""}`}
                      </p>
                    </td>
                    <td role="cell" className={`text-texto-2 max-md:order-last md:text-right ${CELULA}`}>
                      <RotuloItem>Solicitada</RotuloItem>
                      <span>{formatarQuantidade(item.quantidade_solicitada)}</span>
                    </td>
                    <td
                      role="cell"
                      className={`max-md:order-last md:text-right ${CELULA} ${item.divergente ? "font-semibold text-serio-texto" : "text-texto-2"}`}
                    >
                      <RotuloItem>Processada</RotuloItem>
                      <span>{formatarQuantidade(item.quantidade_processada)}</span>
                    </td>
                    <td role="cell" className={`font-medium text-serio-texto max-md:order-last md:text-right ${CELULA}`}>
                      <RotuloItem>Diferença</RotuloItem>
                      <span>{diferenca(item) ?? ""}</span>
                    </td>
                    <td role="cell" className={`text-texto-2 max-md:order-last md:text-right ${CELULA}`}>
                      <RotuloItem>Valor</RotuloItem>
                      <span>{item.valor_total ? formatarMoeda(item.valor_total) : "—"}</span>
                    </td>
                    <td role="cell" className={`max-md:text-right ${CELULA}`}>
                      {item.divergente ? (
                        <StatusBadge tom="serio">Divergente</StatusBadge>
                      ) : item.quantidade_processada === null ? (
                        <StatusBadge tom="neutro">Não processado</StatusBadge>
                      ) : (
                        <StatusBadge tom="bom">Conferido</StatusBadge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
