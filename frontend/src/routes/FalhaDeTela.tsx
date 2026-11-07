import { RefreshCw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";


export function ehFalhaDeCarga(erro: unknown): boolean {
  return (
    erro instanceof Error &&
    /dynamically imported module|Importing a module script failed|error loading dynamically|Loading chunk/i.test(erro.message)
  );
}

interface Props {

  chave: string;
  children: ReactNode;
}

interface Estado {
  erro: unknown;
  chave: string;
}


export class FalhaDeTela extends Component<Props, Estado> {
  state: Estado = { erro: null, chave: this.props.chave };

  static getDerivedStateFromError(erro: unknown): Partial<Estado> {
    return { erro };
  }

  static getDerivedStateFromProps(props: Props, estado: Estado): Partial<Estado> | null {
    return props.chave !== estado.chave ? { erro: null, chave: props.chave } : null;
  }

  componentDidCatch(erro: unknown, info: ErrorInfo) {
    console.error("Falha ao exibir a tela", erro, info.componentStack);
  }

  render() {
    if (!this.state.erro) return this.props.children;

    const carga = ehFalhaDeCarga(this.state.erro);
    return (
      <div className="flex min-h-dvh items-center justify-center bg-plano px-4">
        <div
          role="alert"
          className="flex max-w-md flex-col items-center gap-3 rounded-painel border border-borda bg-superficie p-6 text-center shadow-painel"
        >
          <h1 className="text-lg font-bold text-texto">
            {carga ? "Não foi possível abrir esta tela" : "Algo deu errado nesta tela"}
          </h1>
          <p className="text-sm text-texto-2">
            {carga
              ? "A conexão caiu ou o sistema foi atualizado. Recarregue a página para continuar."
              : "Recarregue a página. Se o erro continuar, avise o administrador do sistema."}
          </p>
          <button type="button" onClick={() => window.location.reload()} className="btn btn-primario mt-2">
            <RefreshCw aria-hidden className="size-4" />
            Recarregar página
          </button>
        </div>
      </div>
    );
  }
}
