import { ArrowRight, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { EmptyState } from "../../../components/ui/EmptyState";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { formatarNumero, nomeCurtoEmpresa, tempoRelativo } from "../../../lib/format";
import { ROTULO_EMPRESA, tomDaEmpresa, type Tom } from "../../../lib/status";
import type { LimitesHoras, NivelStatusEmpresa, StatusEmpresa } from "../../../types/api";


const FAIXA_TOM: Record<Tom, string> = {
  bom: "before:bg-bom/60",
  aviso: "before:bg-aviso",
  serio: "before:bg-serio",
  critico: "before:bg-critico",
  info: "before:bg-info",
  neutro: "before:bg-borda-forte",
};

const ORDEM_NIVEL: Record<string, number> = { critico: 0, atencao: 1, ok: 2 };
const NIVEIS: NivelStatusEmpresa[] = ["critico", "atencao", "ok"];


export function ordenarPorGravidade(itens: StatusEmpresa[]): StatusEmpresa[] {
  return [...itens].sort(
    (a, b) =>
      (ORDEM_NIVEL[a.status] ?? 3) - (ORDEM_NIVEL[b.status] ?? 3) ||
      b.com_erro - a.com_erro ||
      b.pendentes_criticas - a.pendentes_criticas ||
      b.pendentes_atrasadas - a.pendentes_atrasadas ||
      b.pendentes - a.pendentes ||
      a.empresa.codigo.localeCompare(b.empresa.codigo),
  );
}


const LIMITES_PADRAO: LimitesHoras = { horas_atencao: 24, horas_critico: 48 };


export function CompanyStatusList({ itens, limites = LIMITES_PADRAO }: { itens: StatusEmpresa[]; limites?: LimitesHoras }) {
  const [filtro, setFiltro] = useState<NivelStatusEmpresa | null>(null);
  if (itens.length === 0) return <EmptyState titulo="Nenhuma empresa ativa" />;

  const contagem = Object.fromEntries(NIVEIS.map((n) => [n, itens.filter((s) => s.status === n).length])) as Record<
    NivelStatusEmpresa,
    number
  >;
  const visiveis = ordenarPorGravidade(filtro ? itens.filter((s) => s.status === filtro) : itens);
  const comProblema = visiveis.filter((s) => s.status !== "ok");
  const emDia = visiveis.filter((s) => s.status === "ok");

  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Filtrar empresas pela situação" className="grid grid-cols-3 gap-2 sm:max-w-xl">
        {NIVEIS.map((nivel) => {
          const tom = tomDaEmpresa(nivel);
          const ativo = filtro === nivel;
          return (
            <button
              key={nivel}
              type="button"
              aria-pressed={ativo}
              disabled={contagem[nivel] === 0}
              onClick={() => setFiltro(ativo ? null : nivel)}
              className={`flex flex-col items-start rounded-md border px-3 py-2 text-left transition-colors active:translate-y-px disabled:cursor-default disabled:opacity-50 ${
                ativo ? "border-texto bg-superficie-2" : "border-borda hover:border-borda-forte enabled:hover:bg-superficie-2"
              }`}
            >
              <span className="tabular font-display text-2xl font-extrabold leading-none text-texto">{contagem[nivel]}</span>
              <StatusBadge tom={tom} className="mt-1.5">
                {ROTULO_EMPRESA[nivel]}
              </StatusBadge>
            </button>
          );
        })}
      </div>

      {comProblema.length > 0 && (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {comProblema.map((s) => (
            <CartaoEmpresa key={s.empresa.id} item={s} limites={limites} />
          ))}
        </ul>
      )}

      {emDia.length > 0 && (
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-bom-texto">
            <CheckCircle2 aria-hidden className="size-3.5" />
            {emDia.length === 1 ? "1 empresa em dia" : `${emDia.length} empresas em dia`}
            <span className="font-normal text-texto-mudo">· sem pendência atrasada nem erro</span>
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {emDia.map((s) => (
              <li
                key={s.empresa.id}
                title={`${s.empresa.nome}: ${s.pendentes} pendentes`}
                className="tabular flex items-center gap-1.5 rounded border border-borda bg-superficie-2/60 px-2 py-1 text-xs text-texto-2"
              >
                <span className="font-semibold text-texto">{s.empresa.codigo}</span>
                {nomeCurtoEmpresa(s.empresa.nome)}
                {s.pendentes > 0 && <span className="text-texto-mudo">· {s.pendentes} pend.</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function CartaoEmpresa({ item: s, limites }: { item: StatusEmpresa; limites: LimitesHoras }) {
  const tom = tomDaEmpresa(s.status);
  const { horas_atencao: a, horas_critico: c } = limites;

  const recentes = Math.max(s.pendentes - s.pendentes_atrasadas, 0);
  const atrasadas = Math.max(s.pendentes_atrasadas - s.pendentes_criticas, 0);
  const criticas = s.pendentes_criticas;
  const total = recentes + atrasadas + criticas;
  const sincronizacao = s.ultima_sincronizacao;

  return (
    <li
      className={`relative flex flex-col overflow-hidden rounded-md border border-borda bg-superficie py-3 pl-4 pr-3 before:absolute before:inset-y-0 before:left-0 before:w-1 ${FAIXA_TOM[tom]}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-texto" title={s.empresa.nome}>
            <span className="tabular text-texto-mudo">{s.empresa.codigo}</span> {nomeCurtoEmpresa(s.empresa.nome)}
          </p>
          {sincronizacao && (
            <p className="text-[11px] text-texto-mudo" title={`Última sincronização: ${sincronizacao.status}`}>
              Sincronizado {tempoRelativo(sincronizacao.fim ?? sincronizacao.inicio)}
              {sincronizacao.status !== "sucesso" && ` · ${sincronizacao.status}`}
            </p>
          )}
        </div>
        <StatusBadge tom={tom}>{ROTULO_EMPRESA[s.status] ?? s.status}</StatusBadge>
      </div>

      <dl className="mt-3 grid grid-cols-4 gap-1 text-center">
        <Numero rotulo="Pendentes" valor={s.pendentes} />
        <Numero rotulo={`> ${a}h`} valor={s.pendentes_atrasadas} tom="aviso" />
        <Numero rotulo={`> ${c}h`} valor={s.pendentes_criticas} tom="critico" />
        <Numero rotulo="Com erro" valor={s.com_erro} tom="critico" />
      </dl>

      {total > 0 && (
        <div
          role="img"
          aria-label={`Idade das pendências: ${recentes} até ${a}h, ${atrasadas} entre ${a} e ${c}h, ${criticas} acima de ${c}h`}
          className="mt-2.5 flex h-1.5 overflow-hidden rounded-full bg-superficie-3"
        >
          <span className="bg-texto-mudo/40" style={{ width: `${(recentes / total) * 100}%` }} />
          <span className="bg-aviso" style={{ width: `${(atrasadas / total) * 100}%` }} />
          <span className="bg-critico" style={{ width: `${(criticas / total) * 100}%` }} />
        </div>
      )}

      {s.motivos.length > 0 && (
        <ul className="mt-2.5 flex flex-col gap-0.5 text-xs text-texto-2">
          {s.motivos.map((m) => (
            <li key={m} className="flex gap-1.5">
              <span aria-hidden className="text-texto-mudo">
                →
              </span>
              {m}
            </li>
          ))}
        </ul>
      )}

      <Link
        to={`/transferencias?empresa=${encodeURIComponent(s.empresa.codigo)}&periodo=tudo`}
        className="mt-auto flex items-center gap-1 self-end pt-2.5 text-xs font-semibold text-texto-2 transition-colors hover:text-texto"
      >
        Ver transferências
        <ArrowRight aria-hidden className="size-3.5" />
      </Link>
    </li>
  );
}

const COR_NUMERO: Record<"aviso" | "critico", string> = {
  aviso: "text-aviso-texto",
  critico: "text-critico-texto",
};

function Numero({ rotulo, valor, tom }: { rotulo: string; valor: number; tom?: "aviso" | "critico" }) {
  const destaque = tom && valor > 0 ? COR_NUMERO[tom] : valor > 0 ? "text-texto" : "text-texto-mudo/60";
  return (

    <div className="flex flex-col-reverse rounded bg-superficie-2/70 px-1 py-1.5">
      <dt className="mt-1 text-[10px] font-medium uppercase tracking-wide text-texto-mudo">{rotulo}</dt>
      <dd className={`tabular font-display text-lg font-bold leading-none ${destaque}`}>{formatarNumero(valor)}</dd>
    </div>
  );
}
