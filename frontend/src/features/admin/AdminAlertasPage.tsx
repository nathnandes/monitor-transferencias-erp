import { CircleCheck, MessageCircle, Pencil, Plus, RotateCcw, Save, Send, Trash2, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router";

import { AppShell } from "../../components/layout/AppShell";
import { Header } from "../../components/layout/Header";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { Modal } from "../../components/ui/Modal";
import { Panel } from "../../components/ui/Panel";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import { tomDaSeveridade } from "../../lib/status";
import {
  criarDestinoAlerta,
  editarDestinoAlerta,
  excluirDestinoAlerta,
  getConfiguracaoAlertas,
  restaurarModeloMensagem,
  restaurarRegraAlerta,
  salvarModeloMensagem,
  salvarRegraAlerta,
} from "../../services/alertasConfigService";
import { getEmpresas } from "../../services/empresasService";
import type {
  ConfiguracaoAlertas,
  DestinoAlerta,
  DestinoAlertaEntrada,
  Empresa,
  RegraAlertaConfig,
  Severidade,
} from "../../types/api";
import { useSessao } from "../auth/AuthContext";
import { AdminAbas } from "./components/AdminAbas";
import { EstoqueBaixoConfig } from "./components/EstoqueBaixoConfig";
import { MensagemAvulsa } from "./components/MensagemAvulsa";
import { ModelosMensagem } from "./components/ModelosMensagem";
import { mensagemErroAdmin } from "./lib/regrasAdmin";

export const TITULO_ADMIN_ALERTAS = "Administração · Alertas";

export const ROTULO_SEVERIDADE_MINIMA: Record<Severidade, string> = {
  INFO: "Tudo",
  WARNING: "Atenção ou mais grave",
  ERROR: "Erro ou mais grave",
  CRITICAL: "Só crítico",
};
const SEVERIDADES_MINIMAS: Severidade[] = ["WARNING", "ERROR", "CRITICAL"];

type Feedback = { tipo: "sucesso" | "erro"; texto: string };

type CanalDestino = DestinoAlerta["canal"];

const ROTULO_CANAL: Record<CanalDestino, string> = {
  telegram: "Telegram",
  whatsapp: "WhatsApp",
};
const CANAIS: CanalDestino[] = ["telegram", "whatsapp"];


function formatarNumero(digitos: string): string {
  const m = /^55(\d{2})(\d{4,5})(\d{4})$/.exec(digitos);
  return m ? `+55 ${m[1]} ${m[2]}-${m[3]}` : `+${digitos}`;
}


function descreverChat(d: DestinoAlerta): string {
  if (d.canal === "whatsapp") return `WhatsApp ${formatarNumero(d.chat_id ?? "")}`;
  return `Telegram ${d.chat_id ?? "· chat do .env (TELEGRAM_CHAT_ID)"}`;
}

function nomesEmpresas(ids: number[], empresas: Empresa[]): string {
  if (ids.length === 0) return "Todas";
  return ids
    .map((id) => {
      const e = empresas.find((x) => x.id === id);
      return e ? `${e.codigo} - ${e.nome}` : `#${id}`;
    })
    .join(", ");
}



const DESTINO_VAZIO: DestinoAlertaEntrada = {
  nome: "",
  canal: "telegram",
  chat_id: "",
  ativo: true,
  severidade_minima: "WARNING",
  empresas: [],
};

interface DestinoModalProps {
  aberto: boolean;
  inicial: DestinoAlerta | null;
  empresas: Empresa[];
  aoFechar: () => void;
  aoSalvar: (dados: DestinoAlertaEntrada) => Promise<void>;
}

function DestinoModal({ aberto, inicial, empresas, aoFechar, aoSalvar }: DestinoModalProps) {
  const [dados, setDados] = useState<DestinoAlertaEntrada>(DESTINO_VAZIO);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const id = useId();
  const padrao = inicial !== null && inicial.chat_id === null;

  useEffect(() => {
    if (!aberto) return;
    setErro(null);
    setDados(
      inicial
        ? {
            nome: inicial.nome,
            canal: inicial.canal,
            chat_id: inicial.canal === "whatsapp" ? formatarNumero(inicial.chat_id ?? "") : (inicial.chat_id ?? ""),
            ativo: inicial.ativo,
            severidade_minima: inicial.severidade_minima,
            empresas: inicial.empresas,
          }
        : DESTINO_VAZIO,
    );
  }, [aberto, inicial]);

  const alternarEmpresa = (empresaId: number, marcado: boolean) =>
    setDados((d) => ({
      ...d,
      empresas: marcado ? [...d.empresas, empresaId] : d.empresas.filter((e) => e !== empresaId),
    }));

  const enviar = async (evento: React.FormEvent) => {
    evento.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      await aoSalvar({ ...dados, chat_id: padrao ? null : (dados.chat_id ?? "").trim() || null });
    } catch (e) {
      setErro(mensagemErroAdmin(e));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Modal aberto={aberto} titulo={inicial ? "Editar destino" : "Novo destino"} aoFechar={aoFechar} variante="central">
      <form onSubmit={enviar} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-nome`} className="text-xs font-medium text-texto-2">
            Nome
          </label>
          <input
            id={`${id}-nome`}
            className="campo"
            value={dados.nome}
            maxLength={100}
            required
            placeholder="Ex.: Grupo do Depósito 02"
            onChange={(e) => setDados((d) => ({ ...d, nome: e.target.value }))}
          />
        </div>
        {!padrao && (
          <div className="flex flex-col gap-1.5">
            <label htmlFor={`${id}-canal`} className="text-xs font-medium text-texto-2">
              Canal
            </label>
            <select
              id={`${id}-canal`}
              className="campo"
              value={dados.canal}
              onChange={(e) => setDados((d) => ({ ...d, canal: e.target.value as CanalDestino }))}
            >
              {CANAIS.map((c) => (
                <option key={c} value={c}>
                  {ROTULO_CANAL[c]}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-chat`} className="text-xs font-medium text-texto-2">
            {dados.canal === "whatsapp" ? "Número do WhatsApp" : "Chat do Telegram"}
          </label>
          {padrao ? (
            <p className="text-sm text-texto-2">
              Usa o chat do <code>.env</code> (<code>TELEGRAM_CHAT_ID</code>).
            </p>
          ) : (
            <>
              <input
                id={`${id}-chat`}
                className="campo"
                value={dados.chat_id ?? ""}
                maxLength={50}
                required
                inputMode={dados.canal === "whatsapp" ? "tel" : undefined}
                placeholder={dados.canal === "whatsapp" ? "+55 11 98765-4321" : "-1001234567890 ou @canal"}
                onChange={(e) => setDados((d) => ({ ...d, chat_id: e.target.value }))}
              />
              <p className="text-[11px] text-texto-mudo">
                {dados.canal === "whatsapp"
                  ? "Com DDI e DDD. Um número por destino (a API da Meta não manda para grupos); veja docs/alertas.md."
                  : "Adicione o bot ao grupo (em canal, como administrador que pode publicar). O número do chat aparece em getUpdates do bot; veja docs/alertas.md."}
              </p>
            </>
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-sev`} className="text-xs font-medium text-texto-2">
            Recebe
          </label>
          <select
            id={`${id}-sev`}
            className="campo"
            value={dados.severidade_minima}
            onChange={(e) => setDados((d) => ({ ...d, severidade_minima: e.target.value as Severidade }))}
          >
            {SEVERIDADES_MINIMAS.map((s) => (
              <option key={s} value={s}>
                {ROTULO_SEVERIDADE_MINIMA[s]}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="flex flex-col gap-1.5">
          <legend className="text-xs font-medium text-texto-2">Empresas</legend>
          <p className="text-[11px] text-texto-mudo">
            Nenhuma marcada = todas. Marcadas: só alertas em que a empresa é origem ou destino. Sincronização
            parada vai para todos.
          </p>
          <ul className="grid gap-0.5 sm:grid-cols-2">
            {empresas.map((e) => (
              <li key={e.id}>
                <label className="flex cursor-pointer items-start gap-2 rounded-md px-1.5 py-1 text-sm text-texto">
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-acento"
                    checked={dados.empresas.includes(e.id)}
                    onChange={(ev) => alternarEmpresa(e.id, ev.target.checked)}
                  />
                  <span>
                    {e.codigo} - {e.nome}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-texto">
          <input
            type="checkbox"
            className="accent-acento"
            checked={dados.ativo}
            onChange={(e) => setDados((d) => ({ ...d, ativo: e.target.checked }))}
          />
          Ligado (desligado não recebe nada)
        </label>
        {erro && (
          <p role="alert" className="text-sm text-critico-texto">
            {erro}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn-primario" disabled={salvando}>
            <Save aria-hidden className="size-4" />
            {salvando ? "Salvando…" : "Salvar destino"}
          </button>
        </div>
      </form>
    </Modal>
  );
}



interface Rascunho {
  ativo: boolean;
  campos: string[];
  destinos: number[];
}

const doServidor = (r: RegraAlertaConfig): Rascunho => ({
  ativo: r.ativo,
  campos: r.campos,
  destinos: r.destinos,
});


function Previa({ regra, campos }: { regra: RegraAlertaConfig; campos: string[] }) {
  const linhas = regra.campos_disponiveis.filter((c) => campos.includes(c.chave));
  return (
    <div className="rounded-lg border border-borda bg-superficie-2/60 p-3 text-xs text-texto-2">
      <p className="mb-1 font-semibold text-texto">Prévia no Telegram</p>
      <p className="font-medium text-texto">🚨 {regra.nome}</p>
      {linhas.length === 0 ? (
        <p className="mt-1 italic text-texto-mudo">Só o título (nenhum campo marcado).</p>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {linhas.map((c) => (
            <li key={c.chave}>
              {c.rotulo}: <span className="text-texto-mudo">…</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

interface RegraCardProps {
  regra: RegraAlertaConfig;
  destinos: DestinoAlerta[];
  aoSalvar: (regra: string, dados: Rascunho) => Promise<void>;
  aoRestaurar: (regra: string) => Promise<void>;
}

function RegraCard({ regra, destinos, aoSalvar, aoRestaurar }: RegraCardProps) {
  const [rascunho, setRascunho] = useState<Rascunho>(() => doServidor(regra));
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => setRascunho(doServidor(regra)), [regra]);

  const alterado = JSON.stringify(rascunho) !== JSON.stringify(doServidor(regra));
  const alternar = (lista: "campos" | "destinos", valor: string | number, marcado: boolean) =>
    setRascunho((r) => {
      const atual = r[lista] as (string | number)[];
      const nova = marcado ? [...atual, valor] : atual.filter((v) => v !== valor);
      return { ...r, [lista]: nova };
    });

  const executar = async (acao: () => Promise<void>) => {
    setOcupado(true);
    setErro(null);
    try {
      await acao();
    } catch (e) {
      setErro(mensagemErroAdmin(e));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <Panel
      titulo={regra.nome}
      subtitulo={regra.descricao}
      acao={
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-texto">
          <input
            type="checkbox"
            className="accent-acento"
            checked={rascunho.ativo}
            onChange={(e) => setRascunho((r) => ({ ...r, ativo: e.target.checked }))}
          />
          {rascunho.ativo ? "Ligado" : "Desligado"}
        </label>
      }
    >
      <div className={`grid gap-5 lg:grid-cols-3 ${rascunho.ativo ? "" : "opacity-60"}`}>
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-texto-mudo">Enviar para</legend>
          {destinos.length === 0 && <p className="text-sm text-texto-mudo">Cadastre um destino acima.</p>}
          {destinos.map((d) => (
            <label key={d.id} className="flex cursor-pointer items-start gap-2 rounded-md px-1.5 py-1 text-sm text-texto">
              <input
                type="checkbox"
                className="mt-0.5 accent-acento"
                checked={rascunho.destinos.includes(d.id)}
                onChange={(e) => alternar("destinos", d.id, e.target.checked)}
              />
              <span>
                {d.nome}
                {!d.ativo && <span className="ml-1 text-[11px] text-texto-mudo">(desligado)</span>}
              </span>
            </label>
          ))}
          {rascunho.destinos.length === 0 && (
            <p className="text-[11px] text-aviso">Sem destino: o alerta aparece no sistema, mas ninguém é avisado.</p>
          )}
        </fieldset>

        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 text-xs font-semibold uppercase tracking-wide text-texto-mudo">
            Informações da mensagem
          </legend>
          {regra.campos_disponiveis.map((c) => (
            <label key={c.chave} className="flex cursor-pointer items-start gap-2 rounded-md px-1.5 py-1 text-sm text-texto">
              <input
                type="checkbox"
                className="mt-0.5 accent-acento"
                checked={rascunho.campos.includes(c.chave)}
                onChange={(e) => alternar("campos", c.chave, e.target.checked)}
              />
              {c.rotulo}
            </label>
          ))}
        </fieldset>

        <div className="flex flex-col gap-3">
          {regra.regra === "transferencia_atrasada" && (
            <p className="text-[11px] text-texto-mudo">
              As horas de atenção e de crítico ficam em{" "}
              <Link to="/transferencias/controle" className="underline">
                Transferências › Controle
              </Link>
              , as mesmas do dashboard e do resumo diário.
            </p>
          )}
          <Previa regra={regra} campos={rascunho.campos} />
        </div>
      </div>

      {erro && (
        <p role="alert" className="mt-3 text-sm text-critico-texto">
          {erro}
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
        {regra.personalizada && (
          <button
            type="button"
            className="btn btn-sm btn-secundario"
            disabled={ocupado}
            onClick={() => void executar(() => aoRestaurar(regra.regra))}
          >
            <RotateCcw aria-hidden className="size-3.5" />
            Voltar ao padrão
          </button>
        )}
        {alterado && (
          <button type="button" className="btn btn-sm btn-secundario" onClick={() => setRascunho(doServidor(regra))}>
            Desfazer
          </button>
        )}
        <button
          type="button"
          className="btn btn-sm btn-primario"
          disabled={!alterado || ocupado}
          onClick={() => void executar(() => aoSalvar(regra.regra, rascunho))}
        >
          <Save aria-hidden className="size-3.5" />
          {ocupado ? "Salvando…" : "Salvar"}
        </button>
      </div>
    </Panel>
  );
}



const SECOES_REGRAS = [
  {
    tipo: "alerta",
    titulo: "Tipos de alerta",
    descricao: "Situações que abrem um alerta e avisam de novo quando resolvem.",
  },
  {
    tipo: "atividade",
    titulo: "Uso do sistema",
    descricao:
      "Login, saída e alterações feitas por alguém. Um aviso por vez, sem \"resolvido\". Começam desligados: ligue os que quiser receber. O histórico completo fica em Administração › Histórico.",
  },
  {
    tipo: "meta",
    titulo: "Metas de vendas",
    descricao:
      "Aviso quando o grupo, uma loja ou um vendedor chega a um marco da meta. As metas e os marcos ficam em Vendas › Metas.",
  },
  {
    tipo: "estoque",
    titulo: "Estoque baixo",
    descricao:
      "Resumo por loja dos produtos que ficaram abaixo do mínimo pelo giro. Dias de venda e horários: painel Estoque baixo, logo abaixo.",
  },
] as const;


export function AdminAlertasPage() {
  const { temModulo } = useSessao();
  const veEmpresas = temModulo("DASHBOARD");
  const carregamento = useAsync((s) => getConfiguracaoAlertas(s), []);
  const empresas = useAsync(
    (s) => (veEmpresas ? getEmpresas(s).catch(() => [] as Empresa[]) : Promise.resolve([] as Empresa[])),
    [veEmpresas],
  );
  const [config, setConfig] = useState<ConfiguracaoAlertas | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [editando, setEditando] = useState<DestinoAlerta | null | "novo">(null);
  const [excluindo, setExcluindo] = useState<DestinoAlerta | null>(null);

  useEffect(() => {
    if (carregamento.data) setConfig(carregamento.data);
  }, [carregamento.data]);

  const listaEmpresas = useMemo(() => empresas.data ?? [], [empresas.data]);

  const aplicar = useCallback((nova: ConfiguracaoAlertas, texto: string) => {
    setConfig(nova);
    setFeedback({ tipo: "sucesso", texto });
  }, []);

  const salvarDestino = async (dados: DestinoAlertaEntrada) => {
    const alvo = editando;
    const nova = alvo && alvo !== "novo" ? await editarDestinoAlerta(alvo.id, dados) : await criarDestinoAlerta(dados);
    setEditando(null);
    aplicar(nova, `Destino "${dados.nome}" salvo.`);
  };

  const excluir = async () => {
    if (!excluindo) return;
    try {
      aplicar(await excluirDestinoAlerta(excluindo.id), `Destino "${excluindo.nome}" excluído.`);
    } catch (e) {
      setFeedback({ tipo: "erro", texto: mensagemErroAdmin(e) });
    } finally {
      setExcluindo(null);
    }
  };

  const header = (
    <Header
      titulo={TITULO_ADMIN_ALERTAS}
      subtitulo="Quem recebe cada alerta no Telegram ou no WhatsApp, com quais informações e com qual texto · somente ADMIN"
      acoes={<AdminAbas />}
      aoAtualizar={carregamento.recarregar}
      atualizando={carregamento.loading}
    />
  );

  return (
    <AppShell header={header}>
      {feedback && (
        <div
          role={feedback.tipo === "erro" ? "alert" : "status"}
          className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${
            feedback.tipo === "erro" ? "border-critico/40 bg-critico/10 text-critico-texto" : "border-bom/40 bg-bom/10 text-texto"
          }`}
        >
          {feedback.tipo === "erro" ? (
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          ) : (
            <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-bom-texto" />
          )}
          <p className="flex-1">
            {feedback.texto}
            {feedback.tipo === "sucesso" && " Vale a partir do próximo ciclo do worker (até 1 minuto)."}
          </p>
          <button type="button" onClick={() => setFeedback(null)} aria-label="Fechar aviso" className="btn btn-fantasma size-8 px-0">
            <X aria-hidden className="size-4" />
          </button>
        </div>
      )}

      {carregamento.error && !config && (
        <ErrorState
          titulo="Falha ao carregar a configuração dos alertas"
          erro={carregamento.error}
          mensagem={mensagemErroAdmin(carregamento.error)}
          aoTentarNovamente={carregamento.recarregar}
        />
      )}
      {!config && !carregamento.error && <LoadingState rotulo="Carregando configuração…" />}

      {config && (
        <>
          <Panel
            titulo="Destinos"
            subtitulo="Grupos, canais ou chats do Telegram e números do WhatsApp que podem receber alertas"
            nivel={2}
            acao={
              <button type="button" className="btn btn-primario" onClick={() => setEditando("novo")}>
                <Plus aria-hidden className="size-4" />
                Novo destino
              </button>
            }
          >
            <ul className="divide-y divide-borda/70">
              {config.destinos.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
                  {d.canal === "whatsapp" ? (
                    <MessageCircle aria-label="WhatsApp" className="size-4 shrink-0 text-texto-mudo" />
                  ) : (
                    <Send aria-label="Telegram" className="size-4 shrink-0 text-texto-mudo" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-texto">
                      {d.nome}
                      {!d.ativo && <StatusBadge tom="neutro" className="ml-2">Desligado</StatusBadge>}
                    </p>
                    <p className="text-xs text-texto-mudo">
                      {descreverChat(d)} · Empresas: {nomesEmpresas(d.empresas, listaEmpresas)}
                    </p>
                  </div>
                  <StatusBadge tom={tomDaSeveridade(d.severidade_minima)}>
                    {ROTULO_SEVERIDADE_MINIMA[d.severidade_minima]}
                  </StatusBadge>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      className="btn btn-sm btn-secundario"
                      aria-label={`Editar destino ${d.nome}`}
                      onClick={() => setEditando(d)}
                    >
                      <Pencil aria-hidden className="size-3.5" />
                      Editar
                    </button>
                    {d.chat_id !== null && (
                      <button
                        type="button"
                        className="btn btn-sm btn-secundario"
                        aria-label={`Excluir destino ${d.nome}`}
                        onClick={() => setExcluindo(d)}
                      >
                        <Trash2 aria-hidden className="size-3.5" />
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Panel>

          <MensagemAvulsa destinos={config.destinos} aoConcluir={(texto) => setFeedback({ tipo: "sucesso", texto })} />

          {SECOES_REGRAS.map((secao) => (
            <section key={secao.tipo} aria-labelledby={`titulo-${secao.tipo}`} className="flex flex-col gap-4">
              <div>
                <h2 id={`titulo-${secao.tipo}`} className="text-[15px] font-semibold text-texto">
                  {secao.titulo}
                </h2>
                <p className="mt-1 text-xs text-texto-mudo">{secao.descricao}</p>
              </div>
              {config.regras
                .filter((r) => r.tipo === secao.tipo)
                .map((r) => (
                  <RegraCard
                    key={r.regra}
                    regra={r}
                    destinos={config.destinos}
                    aoSalvar={async (regra, dados) =>
                      aplicar(await salvarRegraAlerta(regra, dados), `"${r.nome}" salvo.`)
                    }
                    aoRestaurar={async (regra) =>
                      aplicar(await restaurarRegraAlerta(regra), `"${r.nome}" voltou ao padrão.`)
                    }
                  />
                ))}
            </section>
          ))}

          <EstoqueBaixoConfig aoSalvar={(texto) => setFeedback({ tipo: "sucesso", texto })} />

          <ModelosMensagem
            modelos={config.modelos}
            aoSalvar={async (chave, texto) => aplicar(await salvarModeloMensagem(chave, texto), "Mensagem salva.")}
            aoRestaurar={async (chave) =>
              aplicar(await restaurarModeloMensagem(chave), "A mensagem voltou ao texto padrão.")
            }
          />
        </>
      )}

      <DestinoModal
        aberto={editando !== null}
        inicial={editando === "novo" ? null : editando}
        empresas={listaEmpresas}
        aoFechar={() => setEditando(null)}
        aoSalvar={salvarDestino}
      />
      <ConfirmDialog
        aberto={excluindo !== null}
        titulo="Excluir destino?"
        descricao={
          excluindo
            ? `"${excluindo.nome}" deixa de receber alertas. Se ele já recebeu algum, não dá para excluir: desligue em vez disso.`
            : ""
        }
        rotuloConfirmar="Excluir"
        perigo
        aoConfirmar={() => void excluir()}
        aoCancelar={() => setExcluindo(null)}
      />
    </AppShell>
  );
}
