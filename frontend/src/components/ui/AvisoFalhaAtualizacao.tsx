import { ErrorState } from "./ErrorState";

interface AvisoFalhaAtualizacaoProps {

  erro: Error | null;
  aoTentarNovamente?: () => void;
  className?: string;
}


export function AvisoFalhaAtualizacao({ erro, aoTentarNovamente, className }: AvisoFalhaAtualizacaoProps) {
  if (!erro) return null;
  return (
    <ErrorState
      titulo="Não foi possível atualizar: mostrando os dados anteriores"
      erro={erro}
      aoTentarNovamente={aoTentarNovamente}
      className={className}
    />
  );
}
