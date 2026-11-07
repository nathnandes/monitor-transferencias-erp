import { StatusBadge } from "../../../components/ui/StatusBadge";
import { formatarNumero, formatarQuantidade } from "../../../lib/format";
import type { Tom } from "../../../lib/status";
import type { CoberturaEstoque, ContagemCobertura, StatusCobertura } from "../../../types/api";


export const JANELAS_VENDAS = [7, 15, 30, 60, 90] as const;
export const JANELA_PADRAO = 30;

export const STATUS_COBERTURA: StatusCobertura[] = ["ruptura", "critica", "baixa", "adequada", "excesso", "sem_giro"];

export const ROTULO_COBERTURA: Record<StatusCobertura, string> = {
  ruptura: "Ruptura",
  critica: "Crítica",
  baixa: "Baixa",
  adequada: "Adequada",
  excesso: "Excesso",
  sem_giro: "Sem giro",
};

export const DICA_COBERTURA: Record<StatusCobertura, string> = {
  ruptura: "Sem saldo disponível e com venda na janela: está faltando.",
  critica: "Menos de 7 dias de estoque no ritmo de venda atual.",
  baixa: "Entre 7 e 15 dias de estoque.",
  adequada: "Entre 15 e 90 dias de estoque.",
  excesso: "Mais de 90 dias de estoque: capital parado.",
  sem_giro: "Tem saldo e não vendeu nada na janela.",
};

export const TOM_COBERTURA: Record<StatusCobertura, Tom> = {
  ruptura: "critico",
  critica: "serio",
  baixa: "aviso",
  adequada: "bom",
  excesso: "info",
  sem_giro: "neutro",
};

export function SeloCobertura({ status }: { status: StatusCobertura | null }) {
  if (!status) return <span className="text-texto-mudo">—</span>;
  return <StatusBadge tom={TOM_COBERTURA[status]}>{ROTULO_COBERTURA[status]}</StatusBadge>;
}


export function formatarCobertura(dias: string | null): string {
  if (dias === null) return "—";
  const texto = formatarQuantidade(dias);
  return `${texto} ${Number(dias) >= 2 ? "dias" : "dia"}`;
}


export function CelulaCobertura({ item }: { item: CoberturaEstoque }) {
  return (
    <span className="inline-flex flex-col items-start gap-1 md:items-end">
      <span className="whitespace-nowrap text-texto">{formatarCobertura(item.cobertura_dias)}</span>
      {item.excecao ? (
        <StatusBadge tom="neutro">Exceção</StatusBadge>
      ) : (
        <SeloCobertura status={item.status_cobertura} />
      )}
    </span>
  );
}

interface FaixasCoberturaProps {
  contagem: ContagemCobertura | undefined;
  selecionado: StatusCobertura | "";
  carregando?: boolean;
  aoSelecionar: (status: StatusCobertura | "") => void;

  rotulo?: string;
}


export function FaixasCobertura({
  contagem,
  selecionado,
  carregando = false,
  aoSelecionar,
  rotulo = "Filtrar por cobertura",
}: FaixasCoberturaProps) {
  return (
    <div role="group" aria-label={rotulo} className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
      {STATUS_COBERTURA.map((status) => {
        const ativo = selecionado === status;
        return (
          <button
            key={status}
            type="button"
            aria-pressed={ativo}
            title={DICA_COBERTURA[status]}
            onClick={() => aoSelecionar(ativo ? "" : status)}
            className={`flex flex-col items-start gap-1 rounded-lg border px-3 py-2 text-left transition-colors ${
              ativo ? "border-acento bg-superficie-2" : "border-borda hover:bg-superficie-2/60"
            }`}
          >
            <SeloCobertura status={status} />
            <span className={`tabular text-lg font-semibold text-texto ${carregando ? "opacity-60" : ""}`}>
              {contagem ? formatarNumero(contagem[status]) : "…"}
            </span>
          </button>
        );
      })}
    </div>
  );
}
