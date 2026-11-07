import { Ban, CalendarClock, MessageCircle, Repeat, Send, SendHorizontal } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { Panel } from "../../../components/ui/Panel";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { formatarDataHora } from "../../../lib/format";
import type { Tom } from "../../../lib/status";
import {
  cancelarMensagemAvulsa,
  criarMensagemAvulsa,
  listarMensagensAvulsas,
  listarVariaveisMensagem,
  previaMensagemAvulsa,
} from "../../../services/alertasConfigService";
import type { DestinoAlerta, EnvioMensagemAvulsa, MensagemAvulsa as Mensagem } from "../../../types/api";
import { DIAS_SEMANA, descreverDias, TODOS_OS_DIAS } from "../lib/diasSemana";
import { mensagemErroAdmin } from "../lib/regrasAdmin";
import { ModelosSalvos } from "./ModelosSalvos";

export const LIMITE_TEXTO_AVULSA = 4000;
const ESPERA_PREVIA_MS = 500;

const STATUS_ENVIO: Record<EnvioMensagemAvulsa["status"], { rotulo: string; tom: Tom }> = {
  PENDENTE: { rotulo: "Na fila", tom: "info" },
  ENVIADA: { rotulo: "Enviada", tom: "bom" },
  FALHA: { rotulo: "Falhou", tom: "critico" },
  DESCARTADA: { rotulo: "Não enviada", tom: "neutro" },
};

type Modo = "agora" | "data" | "diario";


function agoraLocal(): string {
  const d = new Date();
  d.setSeconds(0, 0);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}


function usePrevia(texto: string) {
  const [previa, setPrevia] = useState<{ texto: string | null; erro: string | null }>({ texto: null, erro: null });
  const temVariavel = /\{\w+\}/.test(texto);
  useEffect(() => {
    if (!temVariavel) {
      setPrevia({ texto: null, erro: null });
      return;
    }
    const controle = new AbortController();
    const espera = setTimeout(() => {
      previaMensagemAvulsa(texto, controle.signal)
        .then((r) => setPrevia({ texto: r.texto, erro: null }))
        .catch((e: unknown) => {
          if (!controle.signal.aborted) setPrevia({ texto: null, erro: mensagemErroAdmin(e) });
        });
    }, ESPERA_PREVIA_MS);
    return () => {
      clearTimeout(espera);
      controle.abort();
    };
  }, [texto, temVariavel]);
  return { ...previa, temVariavel };
}

interface MensagemAvulsaProps {
  destinos: DestinoAlerta[];
  aoConcluir: (texto: string) => void;
}


export function MensagemAvulsa({ destinos, aoConcluir }: MensagemAvulsaProps) {
  const id = useId();
  const lista = useAsync((s) => listarMensagensAvulsas(s), []);
  const variaveis = useAsync((s) => listarVariaveisMensagem(s), []);
  const ativos = destinos.filter((d) => d.ativo);
  const [texto, setTexto] = useState("");
  const [escolhidos, setEscolhidos] = useState<number[]>([]);
  const [modo, setModo] = useState<Modo>("agora");
  const [quando, setQuando] = useState("");
  const [horario, setHorario] = useState("18:00");
  const [dias, setDias] = useState<number[]>(TODOS_OS_DIAS);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [cancelando, setCancelando] = useState<Mensagem | null>(null);
  const areaTexto = useRef<HTMLTextAreaElement>(null);
  const previa = usePrevia(texto);

  const alternar = (destino: number, marcado: boolean) =>
    setEscolhidos((atual) => (marcado ? [...atual, destino] : atual.filter((d) => d !== destino)));
  const alternarDia = (dia: number, marcado: boolean) =>
    setDias((atual) => (marcado ? [...atual, dia].sort((a, b) => a - b) : atual.filter((d) => d !== dia)));

  const inserir = (variavel: string) => {
    const campo = areaTexto.current;
    const marca = `{${variavel}}`;
    const inicio = campo?.selectionStart ?? texto.length;
    const fim = campo?.selectionEnd ?? texto.length;
    setTexto(texto.slice(0, inicio) + marca + texto.slice(fim));
    requestAnimationFrame(() => {
      campo?.focus();
      campo?.setSelectionRange(inicio + marca.length, inicio + marca.length);
    });
  };

  const faltando = !texto.trim()
    ? "Escreva a mensagem."
    : escolhidos.length === 0
      ? "Escolha pelo menos um destino."
      : modo === "data" && !quando
        ? "Escolha a data e a hora."
        : modo === "diario" && !horario
          ? "Escolha o horário."
          : modo === "diario" && dias.length === 0
            ? "Marque pelo menos um dia da semana."
            : null;

  const enviar = async () => {
    if (faltando) {
      setErro(faltando);
      return;
    }
    setOcupado(true);
    setErro(null);
    try {
      await criarMensagemAvulsa({
        texto,
        destinos: escolhidos,
        agendada_para: modo === "data" ? `${quando}:00` : null,
        horario: modo === "diario" ? horario : null,
        dias_semana: modo === "diario" ? dias : TODOS_OS_DIAS,
      });
      const aviso =
        modo === "diario"
          ? `Mensagem programada ${descreverDias(dias)} às ${horario}.`
          : modo === "data"
            ? `Mensagem agendada para ${formatarDataHora(`${quando}:00`)}.`
            : "Mensagem na fila para envio.";
      setTexto("");
      setEscolhidos([]);
      setModo("agora");
      setQuando("");
      lista.recarregar();
      aoConcluir(aviso);
    } catch (e) {
      setErro(mensagemErroAdmin(e));
    } finally {
      setOcupado(false);
    }
  };

  const cancelar = async () => {
    if (!cancelando) return;
    try {
      await cancelarMensagemAvulsa(cancelando.id);
      lista.recarregar();
      aoConcluir(cancelando.horario ? "Mensagem repetida parada." : "Mensagem cancelada.");
    } catch (e) {
      setErro(mensagemErroAdmin(e));
    } finally {
      setCancelando(null);
    }
  };

  const rotuloBotao = ocupado
    ? "Salvando…"
    : modo === "diario"
      ? "Programar mensagem"
      : modo === "data"
        ? "Agendar mensagem"
        : "Enviar agora";

  return (
    <Panel
      titulo="Mensagem avulsa"
      subtitulo="Escreva qualquer informação e mande agora, numa data e hora ou todo dia, pelo WhatsApp ou pelo Telegram de cada destino."
      nivel={2}
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
          <div className="flex flex-col gap-2">
            <ModelosSalvos texto={texto} aoUsar={setTexto} />
            <label htmlFor={`${id}-texto`} className="text-xs font-medium text-texto-2">
              Mensagem
            </label>
            <textarea
              id={`${id}-texto`}
              ref={areaTexto}
              className="campo min-h-40 text-sm"
              value={texto}
              maxLength={LIMITE_TEXTO_AVULSA}
              placeholder={"Ex.: Resumo de hoje ({data} {hora})\nFaturamento líquido: {faturamento_liquido}\nRecebido: {recebido}"}
              onChange={(e) => setTexto(e.target.value)}
            />
            <p className="text-right text-[11px] text-texto-mudo">
              {texto.length}/{LIMITE_TEXTO_AVULSA}
            </p>
            {variaveis.data && variaveis.data.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-[11px] text-texto-mudo">
                  Valores de vendas e do financeiro, calculados na hora do envio (clique para inserir):
                </p>
                <div role="group" aria-label="Inserir valor" className="flex flex-wrap gap-1">
                  {variaveis.data.map((v) => (
                    <button
                      key={v.chave}
                      type="button"
                      className="btn btn-sm btn-secundario text-[11px]"
                      title={`{${v.chave}}, ex.: ${v.exemplo}`}
                      aria-label={`Inserir ${v.rotulo}`}
                      onClick={() => inserir(v.chave)}
                    >
                      {v.rotulo}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {previa.temVariavel && (
              <div className="flex flex-col gap-1">
                <p className="text-xs font-medium text-texto-2">Prévia com os valores de agora</p>
                <div
                  aria-live="polite"
                  aria-label="Prévia da mensagem"
                  className="whitespace-pre-wrap rounded-lg border border-borda bg-superficie-2/60 p-3 text-sm text-texto"
                >
                  {previa.erro ? <span className="text-critico-texto">{previa.erro}</span> : (previa.texto ?? "…")}
                </div>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-4">
            <fieldset className="flex flex-col gap-1">
              <legend className="mb-1 text-xs font-medium text-texto-2">Enviar para</legend>
              {ativos.length === 0 && (
                <p className="text-xs text-texto-mudo">Nenhum destino ligado. Cadastre um em Destinos.</p>
              )}
              {ativos.map((d) => (
                <label key={d.id} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm text-texto">
                  <input
                    type="checkbox"
                    className="accent-acento"
                    checked={escolhidos.includes(d.id)}
                    onChange={(e) => alternar(d.id, e.target.checked)}
                  />
                  {d.canal === "whatsapp" ? (
                    <MessageCircle aria-label="WhatsApp" className="size-3.5 shrink-0 text-texto-mudo" />
                  ) : (
                    <Send aria-label="Telegram" className="size-3.5 shrink-0 text-texto-mudo" />
                  )}
                  {d.nome}
                </label>
              ))}
            </fieldset>

            <fieldset className="flex flex-col gap-1.5">
              <legend className="mb-1 text-xs font-medium text-texto-2">Quando</legend>
              {(
                [
                  ["agora", "Agora"],
                  ["data", "Em uma data e hora"],
                  ["diario", "Todo dia, num horário"],
                ] as const
              ).map(([valor, rotulo]) => (
                <label key={valor} className="flex cursor-pointer items-center gap-2 text-sm text-texto">
                  <input
                    type="radio"
                    className="accent-acento"
                    name={`${id}-quando`}
                    checked={modo === valor}
                    onChange={() => setModo(valor)}
                  />
                  {rotulo}
                </label>
              ))}
              {modo === "data" && (
                <input
                  type="datetime-local"
                  aria-label="Data e hora do envio"
                  className="campo"
                  min={agoraLocal()}
                  value={quando}
                  onChange={(e) => setQuando(e.target.value)}
                />
              )}
              {modo === "diario" && (
                <div className="flex flex-col gap-2">
                  <input
                    type="time"
                    aria-label="Horário do envio"
                    className="campo"
                    value={horario}
                    onChange={(e) => setHorario(e.target.value)}
                  />
                  <div role="group" aria-label="Dias da semana" className="flex flex-wrap gap-1">
                    {DIAS_SEMANA.map((d) => (
                      <label
                        key={d.dia}
                        className="flex cursor-pointer items-center gap-1 rounded-md border border-borda px-1.5 py-0.5 text-xs text-texto"
                      >
                        <input
                          type="checkbox"
                          className="accent-acento"
                          aria-label={d.nome}
                          checked={dias.includes(d.dia)}
                          onChange={(e) => alternarDia(d.dia, e.target.checked)}
                        />
                        {d.curto}
                      </label>
                    ))}
                  </div>
                  <p className="text-[11px] text-texto-mudo">Horário da empresa. Os valores são os do momento de cada envio.</p>
                </div>
              )}
            </fieldset>
          </div>
        </div>

        {erro && (
          <p role="alert" className="text-sm text-critico-texto">
            {erro}
          </p>
        )}
        <div className="flex justify-end">
          <button type="button" className="btn btn-primario" disabled={ocupado} onClick={() => void enviar()}>
            {modo === "diario" ? (
              <Repeat aria-hidden className="size-4" />
            ) : modo === "data" ? (
              <CalendarClock aria-hidden className="size-4" />
            ) : (
              <SendHorizontal aria-hidden className="size-4" />
            )}
            {rotuloBotao}
          </button>
        </div>

        <div className="border-t border-borda/70 pt-4">
          <h3 className="mb-2 text-xs font-medium text-texto-2">Programadas, agendadas e enviadas</h3>
          {lista.error && <p className="text-sm text-critico-texto">{mensagemErroAdmin(lista.error)}</p>}
          {lista.data?.length === 0 && <p className="text-sm text-texto-mudo">Nenhuma mensagem ainda.</p>}
          <ul className="divide-y divide-borda/70">
            {lista.data?.map((m) => {
              const repetida = m.horario !== null;
              const podeParar = !m.cancelada_em && (repetida || m.envios.some((e) => e.status === "PENDENTE"));
              const periodo = descreverDias(m.dias_semana);
              const titulo = repetida
                ? `${periodo.charAt(0).toUpperCase()}${periodo.slice(1)} às ${m.horario?.slice(0, 5)}`
                : formatarDataHora(m.agendada_para);
              return (
                <li key={m.id} className="flex flex-col gap-2 py-3">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    {repetida && <Repeat aria-label="Repete" className="size-3.5 text-texto-mudo" />}
                    <p className="text-sm font-medium text-texto">{titulo}</p>
                    {repetida && !m.cancelada_em && (
                      <p className="text-xs text-texto-mudo">próximo envio: {formatarDataHora(m.agendada_para)}</p>
                    )}
                    <p className="text-xs text-texto-mudo">por {m.criada_por}</p>
                    {m.cancelada_em && <StatusBadge tom="neutro">{repetida ? "Parada" : "Cancelada"}</StatusBadge>}
                    {podeParar && (
                      <button
                        type="button"
                        className="btn btn-sm btn-secundario ml-auto"
                        aria-label={`${repetida ? "Parar" : "Cancelar"} mensagem: ${titulo}`}
                        onClick={() => setCancelando(m)}
                      >
                        <Ban aria-hidden className="size-3.5" />
                        {repetida ? "Parar" : "Cancelar"}
                      </button>
                    )}
                  </div>
                  <p className="line-clamp-3 whitespace-pre-wrap text-sm text-texto-2">{m.texto}</p>
                  {m.envios.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      {repetida && <span className="text-[11px] text-texto-mudo">Último envio:</span>}
                      {m.envios.map((e, i) => (
                        <StatusBadge key={`${e.destino_id}-${i}`} tom={STATUS_ENVIO[e.status].tom}>
                          <span title={e.ultimo_erro ?? undefined}>
                            {e.destino_nome}: {STATUS_ENVIO[e.status].rotulo}
                          </span>
                        </StatusBadge>
                      ))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      <ConfirmDialog
        aberto={cancelando !== null}
        titulo={cancelando?.horario ? "Parar mensagem repetida?" : "Cancelar mensagem?"}
        descricao={
          cancelando?.horario
            ? "Ela deixa de ser enviada nos próximos dias. O que já saiu não volta."
            : "Os destinos que ainda não receberam deixam de receber. O que já saiu não volta."
        }
        rotuloConfirmar={cancelando?.horario ? "Parar envios" : "Cancelar envio"}
        perigo
        aoConfirmar={() => void cancelar()}
        aoCancelar={() => setCancelando(null)}
      />
    </Panel>
  );
}
