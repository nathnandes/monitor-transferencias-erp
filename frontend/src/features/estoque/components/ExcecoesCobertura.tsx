import { Trash2 } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { useAsync } from "../../../hooks/useAsync";
import { formatarDataHora, formatarNumero } from "../../../lib/format";
import {
  getExcecoesCobertura,
  incluirExcecaoCobertura,
  removerExcecaoCobertura,
} from "../../../services/estoqueService";
import type { EmpresaResumo, ExcecaoCobertura } from "../../../types/api";

interface ExcecoesCoberturaProps {
  empresa: EmpresaResumo;

  quantidade: number;

  recarga: number;

  aoMudar: () => void;
}


export function ExcecoesCobertura({
  empresa,
  quantidade,
  recarga,
  aoMudar,
}: ExcecoesCoberturaProps) {
  const [aberto, setAberto] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [motivo, setMotivo] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const ids = { codigo: useId(), motivo: useId() };
  const lista = useAsync(
    (s) =>
      aberto ? getExcecoesCobertura(empresa.codigo, s) : Promise.resolve(null),
    [aberto, empresa.codigo],
    recarga,
  );

  const mudou = aoMudar;

  async function incluir(evento: FormEvent) {
    evento.preventDefault();
    if (!codigo.trim()) {
      setErro("Informe o código do produto.");
      return;
    }
    setEnviando(true);
    setErro(null);
    setAviso(null);
    try {
      const { incluidos } = await incluirExcecaoCobertura({
        empresa: empresa.codigo,
        codigo: codigo.trim(),
        motivo: motivo.trim() || null,
      });
      setAviso(
        incluidos === 0
          ? `O produto ${codigo.trim()} já era exceção.`
          : `${formatarNumero(incluidos)} ${incluidos === 1 ? "item incluído" : "itens incluídos"}.`,
      );
      setCodigo("");
      mudou();
    } catch (e) {
      setErro(
        e instanceof Error ? e.message : "Não foi possível incluir a exceção.",
      );
    } finally {
      setEnviando(false);
    }
  }

  async function remover(x: ExcecaoCobertura) {
    setErro(null);
    setAviso(null);
    try {
      await removerExcecaoCobertura(
        empresa.codigo,
        x.id_produto,
        x.id_subproduto,
      );
      mudou();
    } catch (e) {
      setErro(
        e instanceof Error ? e.message : "Não foi possível tirar a exceção.",
      );
    }
  }

  return (
    <details
      className="rounded-lg border border-borda"
      open={aberto}
      onToggle={(e) => setAberto((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-texto">
        Exceções de falta ({formatarNumero(quantidade)})
        <span className="ml-2 font-normal text-texto-mudo">
          produtos que nesta empresa não contam como falta (só ficam no
          depósito, ou a loja não tem estrutura)
        </span>
      </summary>
      <div className="flex flex-col gap-3 border-t border-borda p-3">
        <form onSubmit={incluir} className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <label
              htmlFor={ids.codigo}
              className="text-xs font-medium text-texto-2"
            >
              Código do produto
            </label>
            <input
              id={ids.codigo}
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              maxLength={50}
              placeholder="Item ou grade"
              className="campo w-40"
            />
          </div>
          <div className="flex min-w-48 flex-1 flex-col gap-1">
            <label
              htmlFor={ids.motivo}
              className="text-xs font-medium text-texto-2"
            >
              Motivo (opcional)
            </label>
            <input
              id={ids.motivo}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={200}
              placeholder="Ex.: só fica no depósito"
              className="campo w-full"
            />
          </div>
          <button
            type="submit"
            disabled={enviando}
            className="btn btn-sm btn-primario"
          >
            {enviando ? "Incluindo…" : "Incluir"}
          </button>
        </form>
        {erro && (
          <p role="alert" className="text-xs text-critico-texto">
            {erro}
          </p>
        )}
        {aviso && (
          <p role="status" className="text-xs text-texto-2">
            {aviso}
          </p>
        )}
        {lista.error ? (
          <ErrorState
            titulo="Falha ao carregar as exceções"
            erro={lista.error}
            aoTentarNovamente={lista.recarregar}
          />
        ) : !lista.data ? (
          <LoadingState rotulo="Carregando as exceções…" />
        ) : lista.data.length === 0 ? (
          <p className="text-xs text-texto-mudo">
            Nenhuma exceção nesta empresa.
          </p>
        ) : (
          <ul
            aria-label={`Exceções de falta · ${empresa.codigo}`}
            className="flex flex-col divide-y divide-borda"
          >
            {lista.data.map((x) => (
              <li
                key={`${x.id_produto}/${x.id_subproduto}`}
                className="flex items-center gap-3 py-2 text-xs"
              >
                <span className="min-w-0 flex-1">
                  <span className="font-semibold text-texto">
                    {x.id_subproduto}
                  </span>
                  {x.descricao && (
                    <span className="text-texto-2"> · {x.descricao}</span>
                  )}
                  {x.motivo && (
                    <span className="block text-texto-2">{x.motivo}</span>
                  )}
                  <span className="block text-texto-mudo">
                    {x.usuario_nome} · {formatarDataHora(x.criado_em)}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => void remover(x)}
                  aria-label={`Tirar ${x.id_subproduto} das exceções`}
                  className="btn btn-sm btn-secundario"
                >
                  <Trash2 aria-hidden className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
