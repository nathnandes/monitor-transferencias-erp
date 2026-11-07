import { PackageSearch, Save } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { LoadingState } from "../../../components/ui/LoadingState";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { formatarDataHora, formatarQuantidade } from "../../../lib/format";
import {
  getEstoqueBaixo,
  getSituacaoEstoqueBaixo,
  salvarEstoqueBaixo,
} from "../../../services/estoqueBaixoService";
import type { ParametrosEstoqueBaixo } from "../../../types/api";
import { mensagemErroAdmin } from "../lib/regrasAdmin";

interface EstoqueBaixoConfigProps {
  aoSalvar: (texto: string) => void;
}


function lerHorarios(texto: string): string[] {
  return texto
    .split(/[;,\s]+/)
    .filter(Boolean)
    .map((h) => {
      const [hora = "", minuto = "00"] = h.replace(/h$/i, "").split(/[:h]/i);
      return `${hora.padStart(2, "0")}:${(minuto || "00").padStart(2, "0")}`;
    });
}


export function EstoqueBaixoConfig({ aoSalvar }: EstoqueBaixoConfigProps) {
  const carregamento = useAsync((s) => getEstoqueBaixo(s), []);
  const [rodada, setRodada] = useState(0);
  const situacao = useAsync((s) => getSituacaoEstoqueBaixo(5, s), [], rodada);
  const [atual, setAtual] = useState<ParametrosEstoqueBaixo | null>(null);
  const [ativo, setAtivo] = useState(true);
  const [dias, setDias] = useState("7");
  const [janela, setJanela] = useState("30");
  const [horarios, setHorarios] = useState("08:00");
  const [porLoja, setPorLoja] = useState<Record<string, string>>({});
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const p = carregamento.data;
    if (!p) return;
    setAtual(p);
    setAtivo(p.configurado ? p.ativo : true);
    setDias(String(p.dias_cobertura));
    setJanela(String(p.janela_dias));
    setHorarios(p.horarios.join(", "));
    setPorLoja(
      Object.fromEntries(
        Object.entries(p.dias_por_empresa).map(([k, v]) => [k, String(v)]),
      ),
    );
  }, [carregamento.data]);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      const salvo = await salvarEstoqueBaixo({
        ativo,
        dias_cobertura: Number(dias),
        janela_dias: Number(janela),
        horarios: lerHorarios(horarios),
        dias_por_empresa: Object.fromEntries(
          Object.entries(porLoja)
            .filter(([, v]) => v.trim() !== "")
            .map(([k, v]) => [k, Number(v)]),
        ),
      });
      setAtual(salvo);
      setRodada((r) => r + 1);
      aoSalvar(
        salvo.ativo
          ? "Aviso de estoque baixo salvo."
          : "Aviso de estoque baixo desligado.",
      );
    } catch (e2) {
      setErro(mensagemErroAdmin(e2));
    } finally {
      setOcupado(false);
    }
  };

  const lojas = situacao.data?.lojas ?? [];

  return (
    <Panel
      titulo="Estoque baixo"
      subtitulo="Mínimo de cada produto = venda média por dia × dias de venda que você quer ter. Só entram produtos que venderam no período do giro."
      nivel={2}
    >
      {!atual &&
        (carregamento.error ? (
          <p role="alert" className="text-sm text-critico-texto">
            {mensagemErroAdmin(carregamento.error)}
          </p>
        ) : (
          <LoadingState rotulo="Carregando…" />
        ))}
      {/* Só depois de carregar: senão o valor salvo chega e sobrescreve o que já foi digitado. */}
      {atual && (
        <form
          onSubmit={(e) => void enviar(e)}
          aria-label="Configuração do estoque baixo"
          className="flex flex-col gap-4"
        >
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-texto">
              <input
                type="checkbox"
                className="accent-acento"
                checked={ativo}
                onChange={(e) => setAtivo(e.target.checked)}
              />
              Avisar no Telegram
            </label>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="eb-dias"
                className="text-xs font-medium text-texto-2"
              >
                Dias de venda em estoque
              </label>
              <input
                id="eb-dias"
                type="number"
                min={1}
                max={365}
                className="campo w-28"
                value={dias}
                onChange={(e) => setDias(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="eb-janela"
                className="text-xs font-medium text-texto-2"
              >
                Giro medido em (dias)
              </label>
              <input
                id="eb-janela"
                type="number"
                min={7}
                max={180}
                className="campo w-28"
                value={janela}
                onChange={(e) => setJanela(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="eb-horarios"
                className="text-xs font-medium text-texto-2"
              >
                Horários do resumo
              </label>
              <input
                id="eb-horarios"
                className="campo w-48"
                placeholder="08:00, 14:00"
                value={horarios}
                onChange={(e) => setHorarios(e.target.value)}
              />
            </div>
          </div>

          {lojas.length > 0 && (
            <fieldset className="flex flex-col gap-1">
              <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-texto-mudo">
                Dias de venda por loja (vazio = o geral)
              </legend>
              <div className="flex flex-wrap gap-3">
                {lojas.map((l) => (
                  <label
                    key={l.empresa_id}
                    className="flex items-center gap-2 text-sm text-texto"
                  >
                    {l.nome}
                    <input
                      type="number"
                      min={1}
                      max={365}
                      aria-label={`Dias de venda da loja ${l.nome}`}
                      className="campo w-20"
                      value={porLoja[String(l.empresa_id)] ?? ""}
                      onChange={(e) =>
                        setPorLoja((p) => ({
                          ...p,
                          [String(l.empresa_id)]: e.target.value,
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {erro && (
            <p role="alert" className="text-sm text-critico-texto">
              {erro}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] text-texto-mudo">
              {atual?.configurado
                ? `Alterado por ${atual.atualizado_por ?? "—"} em ${formatarDataHora(atual.atualizado_em)}. Último resumo: ${
                    atual.ultima_execucao
                      ? formatarDataHora(atual.ultima_execucao)
                      : "ainda não saiu"
                  }.`
                : "Ainda não configurado: nada é avisado. O primeiro resumo traz todos os produtos que estiverem baixos."}
            </p>
            <button
              type="submit"
              className="btn btn-primario"
              disabled={ocupado}
            >
              <Save aria-hidden className="size-4" />
              {ocupado ? "Salvando…" : "Salvar"}
            </button>
          </div>
        </form>
      )}

      {lojas.length > 0 && (
        <section
          aria-label="Abaixo do mínimo agora"
          className="mt-5 flex flex-col gap-3"
        >
          <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-texto-mudo">
            <PackageSearch aria-hidden className="size-3.5" />
            Abaixo do mínimo agora
            {atual?.configurado
              ? ""
              : " (com os valores padrão, antes de salvar)"}
          </h3>
          {situacao.loading && !situacao.data && (
            <p className="text-sm text-texto-mudo">Calculando…</p>
          )}
          {lojas.map((l) => (
            <div
              key={l.empresa_id}
              className="rounded-lg border border-borda p-3"
            >
              <p className="text-sm font-medium text-texto">
                {l.nome}:{" "}
                {l.total === 0
                  ? "nenhum produto"
                  : `${l.total} produto${l.total === 1 ? "" : "s"}`}
                <span className="ml-1 text-xs font-normal text-texto-mudo">
                  (mínimo para {l.dias} dias)
                </span>
              </p>
              {l.produtos.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-xs text-texto-2">
                  {l.produtos.map((p) => (
                    <li key={`${p.id_produto}-${p.id_subproduto}`}>
                      {p.id_subproduto} {p.descricao ?? ""}: tem{" "}
                      {formatarQuantidade(String(p.disponivel))}, mínimo{" "}
                      {formatarQuantidade(String(p.minimo))}
                    </li>
                  ))}
                  {l.total > l.produtos.length && (
                    <li className="text-texto-mudo">
                      … e mais {l.total - l.produtos.length}
                    </li>
                  )}
                </ul>
              )}
            </div>
          ))}
        </section>
      )}
    </Panel>
  );
}
