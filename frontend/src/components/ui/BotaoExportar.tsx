import { Download, LoaderCircle } from "lucide-react";
import { useState } from "react";

import { baixarArquivo, type Params } from "../../services/apiClient";


export const LIMITE_EXPORTACAO = 50_000;

interface BotaoExportarProps {

  caminho: string;

  params: Params;
  rotulo?: string;
}


export function BotaoExportar({ caminho, params, rotulo = "Exportar" }: BotaoExportarProps) {
  const [baixando, setBaixando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const exportar = async () => {
    setBaixando(true);
    setAviso(null);
    try {
      const { total } = await baixarArquivo(caminho, params);
      if (total !== null && total > LIMITE_EXPORTACAO) {
        setAviso(`Arquivo com os primeiros ${LIMITE_EXPORTACAO.toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")}. Filtre mais.`);
      }
    } catch (erro) {
      setAviso(erro instanceof Error ? erro.message : "Não foi possível exportar.");
    } finally {
      setBaixando(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button type="button" className="btn btn-secundario shrink-0" onClick={exportar} disabled={baixando} title="Baixar em CSV (abre no Excel)">
        {baixando ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : <Download aria-hidden className="size-4" />}
        {baixando ? "Exportando..." : rotulo}
      </button>
      {aviso && (
        <p role="status" className="max-w-64 text-right text-[11px] text-aviso-texto">
          {aviso}
        </p>
      )}
    </div>
  );
}
