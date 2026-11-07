import { CircleAlert, TriangleAlert } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";

import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { formatarDataHora } from "../../../lib/format";
import { getLimites, salvarLimites } from "../../../services/controleTransferenciasService";

const MAXIMO = 720;

interface LimitesPendenciaPanelProps {
  ehAdmin: boolean;

  aoSalvar: () => void;
}

interface CampoProps {
  id: string;
  rotulo: string;
  icone: ReactNode;
  valor: string;
  aoMudar: (valor: string) => void;
  desabilitado: boolean;
}


export function LimitesPendenciaPanel({ ehAdmin, aoSalvar }: LimitesPendenciaPanelProps) {
  const [rodada, setRodada] = useState(0);
  const atuais = useAsync((s) => getLimites(s), [], rodada);
  const [atencao, setAtencao] = useState("");
  const [critico, setCritico] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [mensagem, setMensagem] = useState<{ tom: "ok" | "erro"; texto: string } | null>(null);



  const [vistos, setVistos] = useState(atuais.data);
  if (atuais.data !== vistos) {
    setVistos(atuais.data);
    if (atuais.data) {
      setAtencao(String(atuais.data.horas_atencao));
      setCritico(String(atuais.data.horas_critico));
    }
  }

  const dados = atuais.data;
  const alterado = Boolean(dados) && (atencao !== String(dados?.horas_atencao) || critico !== String(dados?.horas_critico));

  async function salvar(e: FormEvent) {
    e.preventDefault();
    const a = Number(atencao);
    const c = Number(critico);
    if (!Number.isInteger(a) || !Number.isInteger(c) || a < 1 || c > MAXIMO || a >= c) {
      setMensagem({ tom: "erro", texto: `Use horas inteiras, com a atenção menor que o crítico, entre 1 e ${MAXIMO}.` });
      return;
    }
    setSalvando(true);
    setMensagem(null);
    try {
      await salvarLimites({ horas_atencao: a, horas_critico: c });
      setMensagem({ tom: "ok", texto: "Limites salvos. Valem a partir do próximo ciclo dos alertas." });
      setRodada((r) => r + 1);
      aoSalvar();
    } catch (erro) {
      setMensagem({ tom: "erro", texto: erro instanceof Error ? erro.message : "Não foi possível salvar." });
    } finally {
      setSalvando(false);
    }
  }

  const origem = dados?.definido_por
    ? `Definido por ${dados.definido_por}${dados.atualizado_em ? ` em ${formatarDataHora(dados.atualizado_em)}` : ""}.`
    : "Padrão do sistema (24 h e 48 h).";

  return (
    <Panel
      titulo="Atenção e crítico das transferências"
      subtitulo={`Horas sem entrada no destino. Valem para os alertas, o status por empresa do dashboard, o resumo diário e o prazo padrão das rotas. ${
        ehAdmin ? "" : "Só administradores alteram."
      }`}
    >
      {atuais.error && !dados ? (
        <p role="alert" className="text-sm text-critico-texto">
          Não foi possível carregar os limites: {atuais.error.message}
        </p>
      ) : !dados ? (
        <p className="text-sm text-texto-mudo">Carregando…</p>
      ) : (
        <form onSubmit={salvar} className="flex flex-col gap-3">
          <div className="flex flex-wrap items-end gap-4">
            <Campo id="limite-atencao" rotulo="Atenção após" icone={<TriangleAlert aria-hidden className="size-4 text-aviso-texto" />} valor={atencao} aoMudar={setAtencao} desabilitado={!ehAdmin} />
            <Campo id="limite-critico" rotulo="Crítico após" icone={<CircleAlert aria-hidden className="size-4 text-critico-texto" />} valor={critico} aoMudar={setCritico} desabilitado={!ehAdmin} />
            {ehAdmin && (
              <button type="submit" className="btn btn-sm btn-primario" disabled={!alterado || salvando}>
                {salvando ? "Salvando…" : "Salvar"}
              </button>
            )}
          </div>
          <p className="text-[11px] text-texto-mudo">{origem}</p>
          {mensagem && (
            <p role={mensagem.tom === "erro" ? "alert" : "status"} className={`text-xs ${mensagem.tom === "erro" ? "text-critico-texto" : "text-bom-texto"}`}>
              {mensagem.texto}
            </p>
          )}
        </form>
      )}
    </Panel>
  );
}

function Campo({ id, rotulo, icone, valor, aoMudar, desabilitado }: CampoProps) {
  return (
    <span className="flex flex-col gap-1">
      <label htmlFor={id} className="flex items-center gap-1.5 text-xs font-medium text-texto-2">
        {icone}
        {rotulo}
      </label>
      <span className="flex items-center gap-1 text-xs text-texto-mudo">
        <input
          id={id}
          type="number"
          inputMode="numeric"
          min={1}
          max={MAXIMO}
          value={valor}
          disabled={desabilitado}
          onChange={(e) => aoMudar(e.target.value)}
          className="tabular h-8 w-20 rounded-md border border-borda bg-superficie px-2 text-right text-sm text-texto disabled:bg-superficie-2"
        />
        h
      </span>
    </span>
  );
}
