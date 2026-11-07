import { LoaderCircle } from "lucide-react";

interface LoadingStateProps {
  rotulo?: string;

  altura?: number;
}

export function LoadingState({ rotulo = "Carregando...", altura }: LoadingStateProps) {
  return (
    <div
      role="status"
      style={altura ? { minHeight: altura } : undefined}
      className="flex items-center justify-center gap-3 py-8 text-sm text-texto-mudo"
    >
      <LoaderCircle aria-hidden className="size-5 animate-spin text-texto-mudo" />
      {rotulo}
    </div>
  );
}
