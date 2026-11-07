import { BookmarkPlus, Trash2 } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { useAsync } from "../../../hooks/useAsync";
import {
  excluirModeloMensagemAvulsa,
  listarModelosMensagemAvulsa,
  salvarModeloMensagemAvulsa,
} from "../../../services/alertasConfigService";
import type { ModeloMensagemAvulsa } from "../../../types/api";
import { mensagemErroAdmin } from "../lib/regrasAdmin";

interface ModelosSalvosProps {

  texto: string;

  aoUsar: (texto: string) => void;
}


export function ModelosSalvos({ texto, aoUsar }: ModelosSalvosProps) {
  const id = useId();
  const carregamento = useAsync((s) => listarModelosMensagemAvulsa(s), []);
  const [modelos, setModelos] = useState<ModeloMensagemAvulsa[]>([]);
  const [escolhido, setEscolhido] = useState<number | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [nome, setNome] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<{ erro: boolean; texto: string } | null>(null);
  const [excluindo, setExcluindo] = useState<ModeloMensagemAvulsa | null>(null);

  useEffect(() => {
    if (carregamento.data) setModelos(carregamento.data);
  }, [carregamento.data]);

  const atual = modelos.find((m) => m.id === escolhido) ?? null;

  const usar = (valor: string) => {
    const modelo = modelos.find((m) => String(m.id) === valor) ?? null;
    setEscolhido(modelo?.id ?? null);
    setAviso(null);
    if (modelo) aoUsar(modelo.texto);
  };

  const abrirSalvar = () => {
    setNome(atual?.nome ?? "");
    setAviso(null);
    setSalvando(true);
  };

  const salvar = async () => {
    if (!texto.trim()) {
      setAviso({ erro: true, texto: "Escreva a mensagem antes de salvar." });
      return;
    }
    if (!nome.trim()) {
      setAviso({ erro: true, texto: "Dê um nome ao modelo." });
      return;
    }
    setOcupado(true);
    try {
      const lista = await salvarModeloMensagemAvulsa(nome, texto);
      setModelos(lista);
      const salvo = lista.find((m) => m.nome.toLowerCase() === nome.trim().replace(/\s+/g, " ").toLowerCase());
      setEscolhido(salvo?.id ?? null);
      setSalvando(false);
      setAviso({ erro: false, texto: `Modelo "${salvo?.nome ?? nome.trim()}" salvo.` });
    } catch (e) {
      setAviso({ erro: true, texto: mensagemErroAdmin(e) });
    } finally {
      setOcupado(false);
    }
  };

  const excluir = async () => {
    if (!excluindo) return;
    try {
      setModelos(await excluirModeloMensagemAvulsa(excluindo.id));
      setEscolhido(null);
      setAviso({ erro: false, texto: `Modelo "${excluindo.nome}" excluído.` });
    } catch (e) {
      setAviso({ erro: true, texto: mensagemErroAdmin(e) });
    } finally {
      setExcluindo(null);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-48 flex-1 flex-col gap-1">
          <label htmlFor={`${id}-modelo`} className="text-xs font-medium text-texto-2">
            Modelo salvo
          </label>
          <select
            id={`${id}-modelo`}
            className="campo"
            value={escolhido ?? ""}
            onChange={(e) => usar(e.target.value)}
          >
            <option value="">{modelos.length ? "Escolha para preencher o texto…" : "Nenhum modelo salvo ainda"}</option>
            {modelos.map((m) => (
              <option key={m.id} value={m.id}>
                {m.nome}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn btn-sm btn-secundario" onClick={abrirSalvar}>
          <BookmarkPlus aria-hidden className="size-3.5" />
          Salvar como modelo
        </button>
        {atual && (
          <button
            type="button"
            className="btn btn-sm btn-secundario"
            aria-label={`Excluir modelo ${atual.nome}`}
            onClick={() => setExcluindo(atual)}
          >
            <Trash2 aria-hidden className="size-3.5" />
          </button>
        )}
      </div>

      {salvando && (
        <div className="flex flex-wrap items-end gap-2 rounded-lg border border-borda bg-superficie-2/60 p-2">
          <div className="flex min-w-48 flex-1 flex-col gap-1">
            <label htmlFor={`${id}-nome`} className="text-xs font-medium text-texto-2">
              Nome do modelo
            </label>
            <input
              id={`${id}-nome`}
              className="campo"
              value={nome}
              maxLength={80}
              placeholder="Ex.: Resumo das 18h"
              onChange={(e) => setNome(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void salvar();
              }}
            />
          </div>
          <button type="button" className="btn btn-sm btn-primario" disabled={ocupado} onClick={() => void salvar()}>
            {ocupado ? "Salvando…" : "Salvar modelo"}
          </button>
          <button type="button" className="btn btn-sm btn-secundario" disabled={ocupado} onClick={() => setSalvando(false)}>
            Fechar
          </button>
          <p className="w-full text-[11px] text-texto-mudo">
            Guarda só o texto. Com um nome que já existe, o texto daquele modelo é substituído.
          </p>
        </div>
      )}

      {aviso && (
        <p role={aviso.erro ? "alert" : "status"} className={`text-xs ${aviso.erro ? "text-critico-texto" : "text-bom-texto"}`}>
          {aviso.texto}
        </p>
      )}
      {carregamento.error && <p className="text-xs text-critico-texto">{mensagemErroAdmin(carregamento.error)}</p>}

      <ConfirmDialog
        aberto={excluindo !== null}
        titulo="Excluir modelo?"
        descricao={
          excluindo
            ? `"${excluindo.nome}" sai da lista. Mensagens já programadas com esse texto continuam sendo enviadas.`
            : ""
        }
        rotuloConfirmar="Excluir"
        perigo
        aoConfirmar={() => void excluir()}
        aoCancelar={() => setExcluindo(null)}
      />
    </div>
  );
}
