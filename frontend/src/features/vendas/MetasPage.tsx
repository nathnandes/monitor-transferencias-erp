import { ArrowLeft, Plus, Save, Target, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router";

import { AppShell } from "../../components/layout/AppShell";
import { Header } from "../../components/layout/Header";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { Panel } from "../../components/ui/Panel";
import { useAsync } from "../../hooks/useAsync";
import { formatarDataHora, formatarMoeda } from "../../lib/format";
import { ApiError } from "../../services/apiClient";
import { getEmpresas } from "../../services/empresasService";
import {
  excluirMeta,
  getMetas,
  getProgressoMetas,
  getVendedoresMeta,
  salvarMarcos,
  salvarMeta,
} from "../../services/metasService";
import type { ConfiguracaoMetas, Empresa, Meta, MetaEntrada, ProgressoMeta, VendedorOpcao } from "../../types/api";
import { useSessao } from "../auth/AuthContext";

export const TITULO_METAS = "Vendas · Metas";


function mensagemErro(erro: unknown): string {
  if (erro instanceof ApiError) {
    if (erro.status === 403) return "Só ADMIN cadastra metas.";
    return erro.message;
  }
  return "Não foi possível concluir. Tente novamente.";
}

type Nivel = MetaEntrada["nivel"];
type Periodo = MetaEntrada["periodo"];

const ROTULO_NIVEL: Record<Nivel, string> = { GRUPO: "Grupo", EMPRESA: "Loja", VENDEDOR: "Vendedor" };
const ROTULO_PERIODO: Record<Periodo, string> = { DIA: "Diária", SEMANA: "Semanal", MES: "Mensal" };
const TITULO_PERIODO: Record<Periodo, string> = { DIA: "Do dia", SEMANA: "Da semana", MES: "Do mês" };
const PERIODOS: Periodo[] = ["DIA", "SEMANA", "MES"];

const TH = "px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-texto-mudo";
const TD = "px-3 py-2.5 align-middle";


const numero = (valor: string | number) => Number(valor);

function BarraMeta({ item }: { item: ProgressoMeta }) {
  const percentual = numero(item.percentual);
  const batida = percentual >= 100;
  return (
    <li className="flex flex-col gap-1.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="font-medium text-texto">
          {item.alvo}
          <span className="ml-2 text-xs font-normal text-texto-mudo">
            {ROTULO_NIVEL[item.nivel]} · {item.rotulo_periodo}
            {item.especifica && " · meta só deste período"}
          </span>
        </p>
        <p className="text-sm tabular-nums text-texto-2">
          {formatarMoeda(String(item.realizado))} de {formatarMoeda(String(item.valor))}{" "}
          <strong className={batida ? "text-bom-texto" : "text-texto"}>({percentual.toFixed(0)}%)</strong>
        </p>
      </div>
      <div
        role="progressbar"
        aria-label={`${item.alvo}: ${percentual.toFixed(0)}% da meta`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(percentual, 100)}
        className="h-2 overflow-hidden rounded-full bg-superficie-2"
      >
        <div
          className={`h-full rounded-full ${batida ? "bg-bom" : "bg-acento"}`}
          style={{ width: `${Math.min(percentual, 100)}%` }}
        />
      </div>
    </li>
  );
}

function Progresso() {
  const [dia, setDia] = useState("");
  const progresso = useAsync((s) => getProgressoMetas(dia, s), [dia]);
  const dados = progresso.data;
  return (
    <Panel
      titulo="Andamento das metas"
      subtitulo="Faturamento bruto (notas não canceladas), como o ranking de lojas e de vendedores."
      nivel={2}
      acao={
        <div className="flex items-center gap-2">
          <label htmlFor="metas-dia" className="text-xs font-medium text-texto-2">
            Dia
          </label>
          <input id="metas-dia" type="date" className="campo" value={dia || (dados?.dia ?? "")} onChange={(e) => setDia(e.target.value)} />
        </div>
      }
    >
      {progresso.error && !dados && (
        <ErrorState titulo="Falha ao carregar o andamento" erro={progresso.error} aoTentarNovamente={progresso.recarregar} />
      )}
      {!dados && !progresso.error && <LoadingState rotulo="Calculando…" />}
      {dados && dados.itens.length === 0 && (
        <EmptyState icone={Target} titulo="Nenhuma meta em vigor" descricao="Cadastre uma meta abaixo." />
      )}
      {dados &&
        PERIODOS.map((periodo) => {
          const itens = dados.itens.filter((i) => i.periodo === periodo);
          if (itens.length === 0) return null;
          return (
            <section key={periodo} aria-label={TITULO_PERIODO[periodo]} className="mb-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-texto-mudo">{TITULO_PERIODO[periodo]}</h3>
              <ul className="divide-y divide-borda/70">
                {itens.map((i) => (
                  <BarraMeta key={i.meta_id} item={i} />
                ))}
              </ul>
            </section>
          );
        })}
    </Panel>
  );
}

interface FormMetaProps {
  empresas: Empresa[];
  vendedores: VendedorOpcao[];
  aoSalvar: (dados: MetaEntrada) => Promise<void>;
}

function FormMeta({ empresas, vendedores, aoSalvar }: FormMetaProps) {
  const [nivel, setNivel] = useState<Nivel>("EMPRESA");
  const [periodo, setPeriodo] = useState<Periodo>("MES");
  const [empresaId, setEmpresaId] = useState("");
  const [vendedor, setVendedor] = useState("");
  const [valor, setValor] = useState("");
  const [soUmPeriodo, setSoUmPeriodo] = useState(false);
  const [referencia, setReferencia] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    const valorNumerico = Number(valor.replace(/\./g, "").replace(",", "."));
    if (!(valorNumerico > 0)) {
      setErro("Informe o valor da meta, maior que zero.");
      return;
    }
    setOcupado(true);
    setErro(null);
    try {
      await aoSalvar({
        nivel,
        periodo,
        valor: valorNumerico.toFixed(2),
        empresa_id: nivel === "EMPRESA" ? Number(empresaId) || null : null,
        id_vendedor: nivel === "VENDEDOR" ? vendedor || null : null,
        referencia: soUmPeriodo && referencia ? referencia : null,
      });
      setValor("");
    } catch (e2) {
      setErro(mensagemErro(e2));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <form onSubmit={(e) => void enviar(e)} className="flex flex-col gap-3 rounded-lg border border-borda p-3" aria-label="Nova meta">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="meta-nivel" className="text-xs font-medium text-texto-2">Para</label>
          <select id="meta-nivel" className="campo" value={nivel} onChange={(e) => setNivel(e.target.value as Nivel)}>
            <option value="GRUPO">O grupo (todas as lojas)</option>
            <option value="EMPRESA">Uma loja</option>
            <option value="VENDEDOR">Um vendedor</option>
          </select>
        </div>
        {nivel === "EMPRESA" && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="meta-empresa" className="text-xs font-medium text-texto-2">Loja</label>
            <select id="meta-empresa" className="campo" value={empresaId} onChange={(e) => setEmpresaId(e.target.value)} required>
              <option value="">Escolha…</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.codigo} - {e.nome}
                </option>
              ))}
            </select>
          </div>
        )}
        {nivel === "VENDEDOR" && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="meta-vendedor" className="text-xs font-medium text-texto-2">Vendedor</label>
            <select id="meta-vendedor" className="campo" value={vendedor} onChange={(e) => setVendedor(e.target.value)} required>
              <option value="">Escolha…</option>
              {vendedores.map((v) => (
                <option key={v.id_erp} value={v.id_erp}>
                  {v.nome}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="meta-periodo" className="text-xs font-medium text-texto-2">Período</label>
          <select id="meta-periodo" className="campo" value={periodo} onChange={(e) => setPeriodo(e.target.value as Periodo)}>
            <option value="DIA">Diária</option>
            <option value="SEMANA">Semanal (segunda a domingo)</option>
            <option value="MES">Mensal</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="meta-valor" className="text-xs font-medium text-texto-2">Valor (R$)</label>
          <input id="meta-valor" className="campo w-40" inputMode="decimal" placeholder="500.000,00" value={valor} onChange={(e) => setValor(e.target.value)} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-texto">
          <input type="checkbox" className="accent-acento" checked={soUmPeriodo} onChange={(e) => setSoUmPeriodo(e.target.checked)} />
          Só em um período específico (ex.: dezembro)
        </label>
        {soUmPeriodo && (
          <input
            type="date"
            aria-label="Data do período específico"
            className="campo"
            value={referencia}
            onChange={(e) => setReferencia(e.target.value)}
            required
          />
        )}
      </div>
      {erro && (
        <p role="alert" className="text-sm text-critico-texto">
          {erro}
        </p>
      )}
      <div className="flex justify-end">
        <button type="submit" className="btn btn-primario" disabled={ocupado}>
          <Plus aria-hidden className="size-4" />
          {ocupado ? "Salvando…" : "Salvar meta"}
        </button>
      </div>
    </form>
  );
}

function Marcos({ marcos, aoSalvar }: { marcos: number[]; aoSalvar: (marcos: number[]) => Promise<void> }) {
  const [texto, setTexto] = useState(marcos.join(", "));
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => setTexto(marcos.join(", ")), [marcos]);
  const salvar = async () => {
    const lista = texto
      .split(/[;,\s]+/)
      .filter(Boolean)
      .map((t) => Number(t.replace("%", "")));
    if (lista.length === 0 || lista.some((n) => !Number.isInteger(n))) {
      setErro("Use números inteiros separados por vírgula, como 50, 80, 100.");
      return;
    }
    setErro(null);
    try {
      await aoSalvar(lista);
    } catch (e) {
      setErro(mensagemErro(e));
    }
  };
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="metas-marcos" className="text-xs font-medium text-texto-2">
        Avisar no Telegram ao chegar em (% da meta)
      </label>
      <div className="flex flex-wrap gap-2">
        <input id="metas-marcos" className="campo w-48" value={texto} onChange={(e) => setTexto(e.target.value)} />
        <button type="button" className="btn btn-secundario" onClick={() => void salvar()}>
          <Save aria-hidden className="size-4" />
          Salvar marcos
        </button>
      </div>
      <p className="text-[11px] text-texto-mudo">
        Cada marco é avisado uma vez por meta e período. Destinos e texto da mensagem: Administração › Alertas ›
        Metas de vendas.
      </p>
      {erro && (
        <p role="alert" className="text-sm text-critico-texto">
          {erro}
        </p>
      )}
    </div>
  );
}

function rotuloReferencia(meta: Meta): string {
  if (!meta.referencia) return "Vale sempre";
  const [ano, mes, dia] = meta.referencia.split("-");
  if (meta.periodo === "MES") return `Só ${mes}/${ano}`;
  if (meta.periodo === "SEMANA") return `Só a semana de ${dia}/${mes}`;
  return `Só ${dia}/${mes}/${ano}`;
}


export function MetasPage() {
  const { usuario } = useSessao();
  const admin = usuario.role === "ADMIN";
  const carregamento = useAsync((s) => getMetas(s), []);
  const empresas = useAsync((s) => (admin ? getEmpresas(s) : Promise.resolve([] as Empresa[])), [admin]);
  const vendedores = useAsync((s) => (admin ? getVendedoresMeta(s) : Promise.resolve([] as VendedorOpcao[])), [admin]);
  const [config, setConfig] = useState<ConfiguracaoMetas | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState<Meta | null>(null);
  const [rodada, setRodada] = useState(0);

  useEffect(() => {
    if (carregamento.data) setConfig(carregamento.data);
  }, [carregamento.data]);

  const aplicar = (nova: ConfiguracaoMetas, texto: string) => {
    setConfig(nova);
    setAviso(texto);
    setRodada((r) => r + 1);
  };

  const excluir = async () => {
    if (!excluindo) return;
    try {
      await excluirMeta(excluindo.id);
      setConfig((c) => (c ? { ...c, metas: c.metas.filter((m) => m.id !== excluindo.id) } : c));
      setAviso(`Meta de ${excluindo.alvo} excluída.`);
      setRodada((r) => r + 1);
    } catch (e) {
      setAviso(mensagemErro(e));
    } finally {
      setExcluindo(null);
    }
  };

  const header = (
    <Header
      titulo={TITULO_METAS}
      subtitulo="Metas diárias, semanais e mensais do grupo, de cada loja e de cada vendedor"
      acoes={
        <Link to="/vendas" className="btn btn-secundario shrink-0">
          <ArrowLeft aria-hidden className="size-4" />
          Painel de vendas
        </Link>
      }
      aoAtualizar={carregamento.recarregar}
      atualizando={carregamento.loading}
    />
  );

  return (
    <AppShell header={header}>
      {aviso && (
        <p role="status" className="rounded-lg border border-borda bg-superficie px-4 py-3 text-sm text-texto">
          {aviso}
        </p>
      )}

      <Progresso key={rodada} />

      {carregamento.error && !config && (
        <ErrorState titulo="Falha ao carregar as metas" erro={carregamento.error} aoTentarNovamente={carregamento.recarregar} />
      )}
      {config && (
        <Panel
          titulo="Metas cadastradas"
          subtitulo={admin ? "Salvar uma meta que já existe (mesmo alvo e período) troca o valor." : "Só ADMIN cadastra metas."}
          nivel={2}
        >
          <div className="flex flex-col gap-4">
            {admin && (
              <>
                <FormMeta
                  empresas={empresas.data ?? []}
                  vendedores={vendedores.data ?? []}
                  aoSalvar={async (dados) => aplicar(await salvarMeta(dados), "Meta salva.")}
                />
                <Marcos marcos={config.marcos} aoSalvar={async (m) => aplicar(await salvarMarcos(m), "Marcos salvos.")} />
              </>
            )}
            {config.metas.length === 0 ? (
              <EmptyState icone={Target} titulo="Nenhuma meta cadastrada" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse text-sm">
                  <caption className="sr-only">Metas cadastradas</caption>
                  <thead className="bg-superficie-2">
                    <tr>
                      <th scope="col" className={TH}>Para</th>
                      <th scope="col" className={TH}>Período</th>
                      <th scope="col" className={TH}>Quando</th>
                      <th scope="col" className={`${TH} text-right`}>Meta</th>
                      <th scope="col" className={TH}>Alterada por</th>
                      {admin && <th scope="col" className={`${TH} text-right`}>Ações</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {config.metas.map((m) => (
                      <tr key={m.id} className="border-t border-borda">
                        <td className={`${TD} text-texto`}>
                          {m.alvo} <span className="text-xs text-texto-mudo">({ROTULO_NIVEL[m.nivel]})</span>
                        </td>
                        <td className={`${TD} text-texto-2`}>{ROTULO_PERIODO[m.periodo]}</td>
                        <td className={`${TD} text-texto-2`}>{rotuloReferencia(m)}</td>
                        <td className={`${TD} text-right tabular-nums text-texto`}>{formatarMoeda(String(m.valor))}</td>
                        <td className={`${TD} text-xs text-texto-mudo`}>
                          {m.atualizado_por} · {formatarDataHora(m.atualizado_em)}
                        </td>
                        {admin && (
                          <td className={`${TD} text-right`}>
                            <button
                              type="button"
                              className="btn btn-sm btn-secundario"
                              aria-label={`Excluir meta de ${m.alvo}`}
                              onClick={() => setExcluindo(m)}
                            >
                              <Trash2 aria-hidden className="size-3.5" />
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Panel>
      )}
      {!config && !carregamento.error && <LoadingState rotulo="Carregando metas…" />}

      <ConfirmDialog
        aberto={excluindo !== null}
        titulo="Excluir meta?"
        descricao={excluindo ? `A meta ${ROTULO_PERIODO[excluindo.periodo].toLowerCase()} de ${excluindo.alvo} deixa de valer.` : ""}
        rotuloConfirmar="Excluir"
        perigo
        aoConfirmar={() => void excluir()}
        aoCancelar={() => setExcluindo(null)}
      />
    </AppShell>
  );
}
