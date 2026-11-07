import { Download, LoaderCircle, Percent } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ehDataValida } from "../../../lib/datas";
import { somarDias, type Intervalo } from "../../../lib/periodo";
import { exportarDescontos } from "../../../services/vendasService";
import type { ParamsVendas } from "../../../types/api";

interface ExportarDescontosProps {

  params: ParamsVendas;
  hoje: string;
}

function esteMes(hoje: string): Intervalo {
  return { inicio: `${hoje.slice(0, 7)}-01`, fim: hoje };
}

function mesPassado(hoje: string): Intervalo {
  const fim = somarDias(esteMes(hoje).inicio, -1);
  return { inicio: `${fim.slice(0, 7)}-01`, fim };
}


export function ExportarDescontos({ params, hoje }: ExportarDescontosProps) {
  const [aberto, setAberto] = useState(false);
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [baixando, setBaixando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const invalido = !ehDataValida(inicio) || !ehDataValida(fim) || inicio > fim;

  const escolher = ({ inicio: de, fim: ate }: Intervalo) => {
    setInicio(de);
    setFim(ate);
    setErro(null);
  };

  const alternar = () => {
    if (!aberto) {
      const daTela = params.data_inicial && params.data_final;
      escolher(daTela ? { inicio: params.data_inicial!, fim: params.data_final! } : esteMes(hoje));
    }
    setAberto((a) => !a);
  };

  const gerar = async (e: FormEvent) => {
    e.preventDefault();
    if (invalido || baixando) return;
    setBaixando(true);
    setErro(null);
    try {
      await exportarDescontos({ data_inicial: inicio, data_final: fim, empresa: params.empresa, canal: params.canal });
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : "Não foi possível exportar.");
    } finally {
      setBaixando(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        className="btn btn-secundario shrink-0"
        aria-expanded={aberto}
        onClick={alternar}
        title="Baixar em Excel os descontos de cada vendedor no período que você escolher"
      >
        <Percent aria-hidden className="size-4" />
        Descontos
      </button>
      {aberto && (
        <form
          onSubmit={gerar}
          onKeyDown={(e) => e.key === "Escape" && setAberto(false)}
          aria-label="Relatório de descontos"
          noValidate
          className="absolute right-0 top-full z-30 mt-2 flex w-72 max-w-[calc(100vw-2rem)] flex-col gap-3 rounded-painel border border-borda bg-superficie p-4 text-left text-texto shadow-lg max-sm:fixed max-sm:inset-x-4 max-sm:top-auto max-sm:w-auto"
        >
          <p className="text-sm font-semibold">Relatório de descontos</p>
          <div className="flex gap-2">
            <button type="button" className="btn btn-fantasma btn-sm" onClick={() => escolher(esteMes(hoje))}>
              Este mês
            </button>
            <button type="button" className="btn btn-fantasma btn-sm" onClick={() => escolher(mesPassado(hoje))}>
              Mês passado
            </button>
          </div>
          <label className="flex flex-col gap-1 text-xs text-texto-2">
            De
            <input
              type="date"
              className="campo h-9"
              value={inicio}
              max={hoje}
              onChange={(e) => setInicio(e.target.value)}
              aria-invalid={!ehDataValida(inicio) || inicio > fim}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-texto-2">
            Até
            <input
              type="date"
              className="campo h-9"
              value={fim}
              max={hoje}
              onChange={(e) => setFim(e.target.value)}
              aria-invalid={!ehDataValida(fim) || inicio > fim}
            />
          </label>
          <p className="text-xs text-texto-mudo">A loja e o canal seguem os filtros da tela.</p>
          {ehDataValida(inicio) && ehDataValida(fim) && inicio > fim && (
            <p role="alert" className="text-xs text-aviso-texto">
              A data inicial é depois da final.
            </p>
          )}
          {erro && (
            <p role="alert" className="text-xs text-aviso-texto">
              {erro}
            </p>
          )}
          <button type="submit" className="btn btn-primario btn-sm" disabled={invalido || baixando}>
            {baixando ? <LoaderCircle aria-hidden className="size-3.5 animate-spin" /> : <Download aria-hidden className="size-3.5" />}
            {baixando ? "Gerando..." : "Baixar Excel"}
          </button>
        </form>
      )}
    </div>
  );
}
