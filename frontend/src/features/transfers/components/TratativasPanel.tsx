import { ClipboardCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { formatarDataHora } from "../../../lib/format";
import { getTratativas, registrarTratativa } from "../../../services/controleTransferenciasService";
import type { SituacaoTratativa } from "../../../types/api";

export const ROTULO_TRATATIVA: Record<SituacaoTratativa, string> = {
  EM_ANALISE: "Em análise",
  RESOLVIDA: "Resolvida",
};


export function TratativasPanel({ id, aoRegistrar }: { id: number; aoRegistrar?: () => void }) {
  const [rodada, setRodada] = useState(0);
  const lista = useAsync((s) => getTratativas(id, s), [id], rodada);
  const [situacao, setSituacao] = useState<SituacaoTratativa>("EM_ANALISE");
  const [observacao, setObservacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (observacao.trim().length < 3) {
      setErro("Descreva o que foi verificado (mínimo de 3 caracteres).");
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      await registrarTratativa(id, { situacao, observacao: observacao.trim() });
      setObservacao("");
      setRodada((r) => r + 1);
      aoRegistrar?.();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível registrar a tratativa.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby={`tratativas-${id}`} className="rounded-lg border border-borda bg-superficie p-4">
      <h3 id={`tratativas-${id}`} className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-texto">
        <ClipboardCheck aria-hidden className="size-4 text-texto-mudo" />
        Tratativa
      </h3>

      <form onSubmit={enviar} className="flex flex-col gap-2">
        <div role="radiogroup" aria-label="Situação" className="flex gap-1.5">
          {(Object.keys(ROTULO_TRATATIVA) as SituacaoTratativa[]).map((s) => (
            <label
              key={s}
              className={`flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-foco ${
                situacao === s ? "border-texto bg-superficie-2 text-texto" : "border-borda text-texto-2 hover:border-borda-forte"
              }`}
            >
              <input type="radio" name={`situacao-${id}`} value={s} checked={situacao === s} onChange={() => setSituacao(s)} className="sr-only" />
              {ROTULO_TRATATIVA[s]}
            </label>
          ))}
        </div>
        <label className="sr-only" htmlFor={`obs-${id}`}>
          O que foi verificado
        </label>
        <textarea
          id={`obs-${id}`}
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          rows={2}
          maxLength={2000}
          placeholder="Ex.: falta de 2 un. confirmada com a loja; nota de devolução emitida."
          className="w-full rounded-md border border-borda bg-superficie px-3 py-2 text-sm text-texto placeholder:text-texto-mudo focus:border-borda-forte"
        />
        {erro && (
          <p role="alert" className="text-xs text-critico-texto">
            {erro}
          </p>
        )}
        <button type="submit" disabled={enviando} className="btn btn-sm btn-primario self-end">
          {enviando ? "Registrando…" : "Registrar"}
        </button>
      </form>

      <div className="mt-4">
        {lista.error ? (
          <ErrorState erro={lista.error} aoTentarNovamente={lista.recarregar} />
        ) : !lista.data ? (
          <LoadingState rotulo="Carregando histórico..." />
        ) : lista.data.length === 0 ? (
          <p className="text-xs text-texto-mudo">Ninguém registrou verificação ainda.</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {lista.data.map((t) => (
              <li key={t.id} className="rounded-md bg-superficie-2 px-3 py-2 text-xs">
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <StatusBadge tom={t.situacao === "RESOLVIDA" ? "bom" : "aviso"}>{ROTULO_TRATATIVA[t.situacao]}</StatusBadge>
                  <span className="font-semibold text-texto">{t.usuario_nome}</span>
                  <span className="text-texto-mudo">{formatarDataHora(t.created_at)}</span>
                </p>
                <p className="mt-1 whitespace-pre-line text-texto-2">{t.observacao}</p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
