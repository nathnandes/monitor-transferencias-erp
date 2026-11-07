import { StatusBadge } from "../../../components/ui/StatusBadge";
import type { Tom } from "../../../lib/status";
import type { CategoriaMovimento } from "../../../types/api";

export const ROTULO_CATEGORIA: Record<CategoriaMovimento, string> = {
  venda: "Venda",
  devolucao_venda: "Devolução de venda",
  compra: "Compra",
  devolucao_compra: "Devolução de compra",
  transferencia_entrada: "Transferência recebida",
  transferencia_saida: "Transferência enviada",
  entrada_avulsa: "Entrada avulsa",
  saida_avulsa: "Saída avulsa",
  balanco: "Balanço",
  perda: "Perda",
  uso_consumo: "Uso e consumo",
  producao: "Produção",
  bonificacao: "Bonificação/doação",
  remessa: "Remessa",
  outros: "Outros",
  nao_classificado: "Não classificado",
};

const TOM_CATEGORIA: Record<CategoriaMovimento, Tom> = {
  venda: "neutro",
  devolucao_venda: "bom",
  compra: "bom",
  devolucao_compra: "aviso",
  transferencia_entrada: "info",
  transferencia_saida: "info",
  entrada_avulsa: "bom",
  saida_avulsa: "aviso",
  balanco: "info",
  perda: "critico",
  uso_consumo: "aviso",
  producao: "neutro",
  bonificacao: "neutro",
  remessa: "neutro",
  outros: "neutro",
  nao_classificado: "serio",
};

export function SeloCategoria({ categoria }: { categoria: CategoriaMovimento }) {
  return <StatusBadge tom={TOM_CATEGORIA[categoria]}>{ROTULO_CATEGORIA[categoria]}</StatusBadge>;
}


export function AvisoAfeta({ afeta }: { afeta: boolean | null }) {
  if (afeta === true) return null;
  return (
    <span className="text-[11px] text-texto-mudo">
      {afeta === false ? "não mexe no estoque" : "a confirmar · fora dos totais"}
    </span>
  );
}
