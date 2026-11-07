import { LoaderCircle } from "lucide-react";
import { useId, type ReactNode } from "react";

import { Modal } from "./Modal";

interface ConfirmDialogProps {
  aberto: boolean;
  titulo: string;
  descricao: ReactNode;
  rotuloConfirmar: string;
  aoConfirmar: () => void;
  aoCancelar: () => void;

  perigo?: boolean;
  processando?: boolean;
}


export function ConfirmDialog({
  aberto,
  titulo,
  descricao,
  rotuloConfirmar,
  aoConfirmar,
  aoCancelar,
  perigo = false,
  processando = false,
}: ConfirmDialogProps) {
  const idDescricao = useId();
  const cancelar = () => {
    if (!processando) aoCancelar();
  };
  return (
    <Modal
      aberto={aberto}
      titulo={titulo}
      aoFechar={cancelar}
      rotuloFechar="Fechar sem confirmar"
      variante="central"
      papel="alertdialog"
      idDescricao={idDescricao}
    >
      <div id={idDescricao} className="text-sm text-texto-2">
        {descricao}
      </div>
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button type="button" onClick={cancelar} disabled={processando} className="btn btn-secundario">
          Cancelar
        </button>
        <button
          type="button"
          onClick={aoConfirmar}
          disabled={processando}
          aria-busy={processando}
          className={
            perigo
              ? "btn bg-critico font-semibold text-white enabled:hover:bg-critico/85"
              : "btn btn-primario"
          }
        >
          {processando && <LoaderCircle aria-hidden className="size-4 animate-spin" />}
          {rotuloConfirmar}
        </button>
      </div>
    </Modal>
  );
}
