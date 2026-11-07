import { RotateCcw, Save, Undo2 } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Panel } from "../../../components/ui/Panel";
import { formatarDataHora } from "../../../lib/format";
import { previaModeloMensagem } from "../../../services/alertasConfigService";
import type { ModeloMensagemAlerta } from "../../../types/api";
import { mensagemErroAdmin } from "../lib/regrasAdmin";


const ESPERA_PREVIA_MS = 400;

interface ModelosMensagemProps {
  modelos: ModeloMensagemAlerta[];
  aoSalvar: (chave: string, texto: string) => Promise<void>;
  aoRestaurar: (chave: string) => Promise<void>;
}


function usePrevia(chave: string, texto: string) {
  const [previa, setPrevia] = useState<{ texto: string | null; erro: string | null }>({ texto: null, erro: null });
  useEffect(() => {
    const controle = new AbortController();
    const espera = setTimeout(() => {
      previaModeloMensagem(chave, texto, controle.signal)
        .then((r) => setPrevia({ texto: r.texto, erro: null }))
        .catch((e: unknown) => {
          if (!controle.signal.aborted) setPrevia({ texto: null, erro: mensagemErroAdmin(e) });
        });
    }, ESPERA_PREVIA_MS);
    return () => {
      clearTimeout(espera);
      controle.abort();
    };
  }, [chave, texto]);
  return previa;
}


export function ModelosMensagem({ modelos, aoSalvar, aoRestaurar }: ModelosMensagemProps) {
  const id = useId();
  const [chave, setChave] = useState(modelos[0]?.chave ?? "");
  const modelo = modelos.find((m) => m.chave === chave) ?? modelos[0];
  const [texto, setTexto] = useState(modelo?.texto ?? "");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const areaTexto = useRef<HTMLTextAreaElement>(null);
  const previa = usePrevia(modelo?.chave ?? "", texto);


  useEffect(() => {
    setTexto(modelo?.texto ?? "");
    setErro(null);
  }, [modelo?.chave, modelo?.texto]);

  const grupos = useMemo(() => {
    const porGrupo = new Map<string, ModeloMensagemAlerta[]>();
    for (const m of modelos) porGrupo.set(m.grupo, [...(porGrupo.get(m.grupo) ?? []), m]);
    return [...porGrupo.entries()];
  }, [modelos]);

  if (!modelo) return null;
  const alterado = texto.trim() !== modelo.texto;

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
      titulo="Mensagens do Telegram"
      subtitulo="O texto de cada mensagem. As variáveis entre chaves viram os dados do alerta na hora do envio."
      nivel={2}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-mensagem`} className="text-xs font-medium text-texto-2">
            Mensagem
          </label>
          <select
            id={`${id}-mensagem`}
            className="campo max-w-xl"
            value={modelo.chave}
            onChange={(e) => setChave(e.target.value)}
          >
            {grupos.map(([grupo, lista]) => (
              <optgroup key={grupo} label={grupo}>
                {lista.map((m) => (
                  <option key={m.chave} value={m.chave}>
                    {m.nome}
                    {m.personalizado ? " (personalizada)" : ""}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <p className="text-[11px] text-texto-mudo">
            {modelo.descricao}{" "}
            {modelo.personalizado
              ? `Personalizada por ${modelo.atualizado_por ?? "—"} em ${formatarDataHora(modelo.atualizado_em)}.`
              : "Usando o texto padrão."}
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="flex flex-col gap-2">
            <label htmlFor={`${id}-texto`} className="text-xs font-medium text-texto-2">
              Texto
            </label>
            <textarea
              id={`${id}-texto`}
              ref={areaTexto}
              className="campo min-h-48 font-mono text-xs"
              value={texto}
              maxLength={3000}
              onChange={(e) => setTexto(e.target.value)}
            />
            <div role="group" aria-label="Inserir variável" className="flex flex-wrap gap-1">
              {modelo.variaveis.map((v) => (
                <button
                  key={v.chave}
                  type="button"
                  className="btn btn-sm btn-secundario font-mono text-[11px]"
                  title={v.rotulo}
                  aria-label={`Inserir ${v.rotulo}`}
                  onClick={() => inserir(v.chave)}
                >
                  {`{${v.chave}}`}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-texto-2">Prévia no Telegram (dados de exemplo)</p>
            <div
              aria-live="polite"
              className="min-h-48 whitespace-pre-wrap rounded-lg border border-borda bg-superficie-2/60 p-3 text-xs text-texto"
            >
              {previa.erro ? <span className="text-critico-texto">{previa.erro}</span> : (previa.texto ?? "…")}
            </div>
          </div>
        </div>

        {erro && (
          <p role="alert" className="text-sm text-critico-texto">
            {erro}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-end gap-2">
          {alterado && (
            <button type="button" className="btn btn-sm btn-secundario" disabled={ocupado} onClick={() => setTexto(modelo.texto)}>
              <Undo2 aria-hidden className="size-3.5" />
              Descartar
            </button>
          )}
          {(modelo.personalizado || texto.trim() !== modelo.padrao) && (
            <button
              type="button"
              className="btn btn-sm btn-secundario"
              disabled={ocupado}
              onClick={() =>
                modelo.personalizado ? void executar(() => aoRestaurar(modelo.chave)) : setTexto(modelo.padrao)
              }
            >
              <RotateCcw aria-hidden className="size-3.5" />
              Voltar ao texto padrão
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm btn-primario"
            disabled={!alterado || ocupado}
            onClick={() => void executar(() => aoSalvar(modelo.chave, texto))}
          >
            <Save aria-hidden className="size-3.5" />
            {ocupado ? "Salvando…" : "Salvar mensagem"}
          </button>
        </div>
      </div>
    </Panel>
  );
}
