import { Timer } from "lucide-react";
import { useState } from "react";

import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { nomeCurtoEmpresa } from "../../../lib/format";
import { getPrazos, salvarPrazos } from "../../../services/controleTransferenciasService";
import type { PrazoRota, RotaControle } from "../../../types/api";

interface PrazosRotaPanelProps {

  rotas: RotaControle[];
  padrao: number;
  ehAdmin: boolean;
  aoSalvar: () => void;
}

const SEPARADOR = ">";
const chave = (o: string, d: string) => `${o}${SEPARADOR}${d}`;

const daChave = (k: string) => {
  const [origem = "", destino = ""] = k.split(SEPARADOR);
  return { origem, destino };
};


export function PrazosRotaPanel({ rotas, padrao, ehAdmin, aoSalvar }: PrazosRotaPanelProps) {
  const [rodada, setRodada] = useState(0);
  const atuais = useAsync((s) => getPrazos(s), [], rodada);
  const [editados, setEditados] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [mensagem, setMensagem] = useState<{ tom: "ok" | "erro"; texto: string } | null>(null);

  const cadastrados = new Map((atuais.data?.prazos ?? []).map((p) => [chave(p.origem, p.destino), p.horas]));


  const [prazosVistos, setPrazosVistos] = useState(atuais.data);
  if (atuais.data !== prazosVistos) {
    setPrazosVistos(atuais.data);
    setEditados({});
  }


  const linhas = new Map<string, { origem: string; destino: string; nome: string }>();
  for (const r of rotas) {
    linhas.set(chave(r.origem.codigo, r.destino.codigo), {
      origem: r.origem.codigo,
      destino: r.destino.codigo,
      nome: `${nomeCurtoEmpresa(r.origem.nome)} → ${nomeCurtoEmpresa(r.destino.nome)}`,
    });
  }
  for (const p of atuais.data?.prazos ?? []) {
    const k = chave(p.origem, p.destino);
    if (!linhas.has(k)) linhas.set(k, { origem: p.origem, destino: p.destino, nome: "" });
  }
  const ordenadas = [...linhas.entries()].sort(([a], [b]) => a.localeCompare(b));
  const alteradas = Object.keys(editados);

  async function salvar() {
    const corpo: PrazoRota[] = [];


    for (const [k, valor] of Object.entries(editados)) {
      const { origem, destino } = daChave(k);
      const texto = valor.trim();
      const horas = texto === "" ? null : Number(texto);
      if (horas !== null && (!Number.isInteger(horas) || horas < 1 || horas > 720)) {
        setMensagem({ tom: "erro", texto: `Prazo de ${origem} → ${destino}: use horas inteiras entre 1 e 720.` });
        return;
      }
      corpo.push({ origem, destino, horas });
    }
    setSalvando(true);
    setMensagem(null);
    try {
      await salvarPrazos(corpo);
      setMensagem({ tom: "ok", texto: "Prazos salvos." });
      setRodada((r) => r + 1);
      aoSalvar();
    } catch (e) {
      setMensagem({ tom: "erro", texto: e instanceof Error ? e.message : "Não foi possível salvar." });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Panel
      titulo="Prazo de entrega por rota"
      subtitulo={`Horas entre a saída e a entrada no destino. Vazio = padrão de ${padrao} h. ${
        ehAdmin ? "" : "Só administradores alteram."
      }`}
      acao={
        ehAdmin && (
          <button type="button" className="btn btn-sm btn-primario" disabled={!alteradas.length || salvando} onClick={salvar}>
            {salvando ? "Salvando…" : `Salvar${alteradas.length ? ` (${alteradas.length})` : ""}`}
          </button>
        )
      }
    >
      {mensagem && (
        <p role={mensagem.tom === "erro" ? "alert" : "status"} className={`mb-3 text-xs ${mensagem.tom === "erro" ? "text-critico-texto" : "text-bom-texto"}`}>
          {mensagem.texto}
        </p>
      )}
      {ordenadas.length === 0 ? (
        <p className="text-sm text-texto-mudo">Nenhuma rota com movimento no período.</p>
      ) : (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {ordenadas.map(([k, l]) => {
            const valor = editados[k] ?? String(cadastrados.get(k) ?? "");
            const id = `prazo-${l.origem}-${l.destino}`;
            return (
              <li key={k} className="flex items-center gap-3 rounded-md border border-borda px-3 py-2">
                <Timer aria-hidden className="size-4 shrink-0 text-texto-mudo" />
                <label htmlFor={id} className="min-w-0 flex-1 text-sm">
                  <span className="tabular font-semibold text-texto">
                    {l.origem} → {l.destino}
                  </span>
                  {l.nome && <span className="block truncate text-[11px] text-texto-mudo">{l.nome}</span>}
                </label>
                <span className="flex items-center gap-1 text-xs text-texto-mudo">
                  <input
                    id={id}
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={720}
                    value={valor}
                    placeholder={String(padrao)}
                    disabled={!ehAdmin}
                    onChange={(e) => setEditados((atual) => ({ ...atual, [k]: e.target.value }))}
                    className="tabular h-8 w-16 rounded-md border border-borda bg-superficie px-2 text-right text-sm text-texto disabled:bg-superficie-2"
                  />
                  h
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
