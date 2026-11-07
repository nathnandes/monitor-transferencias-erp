import { formatarMoedaNumero, formatarNumero } from "../../../lib/format";
import type { FormaRecebida } from "../../../types/api";
import { nomeForma, paraNumero } from "../lib/financeiro";


export function RecebidosPorForma({ dados }: { dados: FormaRecebida[] }) {
  const maior = Math.max(...dados.map((f) => paraNumero(f.valor)), 0);
  return (
    <ul
      className="flex flex-col gap-3"
      aria-label="Recebido por forma de pagamento"
    >
      {dados.map((f) => {
        const valor = paraNumero(f.valor);
        return (
          <li key={f.forma} className="flex flex-col gap-1 text-sm">
            <div className="flex items-center gap-3">
              <span
                className="min-w-0 flex-1 truncate text-texto"
                title={f.forma}
              >
                {nomeForma(f.forma)}
              </span>
              <span className="tabular text-xs text-texto-mudo">
                {formatarNumero(f.titulos)} parc.
              </span>
              <span className="tabular w-28 text-right font-bold text-texto">
                {formatarMoedaNumero(valor)}
              </span>
            </div>
            <div aria-hidden className="h-1.5 rounded-full bg-superficie-2">
              <div
                className="h-full rounded-full bg-[#2f6fde]"
                style={{ width: `${maior > 0 ? (valor / maior) * 100 : 0}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
