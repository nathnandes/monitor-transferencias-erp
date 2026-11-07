import { ArrowRight, Siren } from "lucide-react";
import { useEffect, useState, type MouseEvent } from "react";
import { Link } from "react-router";

import { useSessaoOpcional } from "../../features/auth/AuthContext";
import { useAsync } from "../../hooks/useAsync";
import { gravarBusca } from "../../hooks/useBuscaDaUrl";
import { formatarNumero } from "../../lib/format";
import { getTransferenciasSemCoi } from "../../services/coiService";


export const INTERVALO_AVISO_COI_MS = 30_000;


export const ROTA_SEM_COI = "/transferencias?periodo=tudo&situacao_coi=ERRADO";


function irParaSemCoi(destino: string) {
  return (e: MouseEvent<HTMLAnchorElement>) => {
    const [caminho, busca = ""] = destino.split("?");
    if (window.location.pathname !== caminho) return;
    e.preventDefault();
    gravarBusca(new URLSearchParams(busca), "push");
  };
}

interface AvisoSemCoiProps {

  variante?: "padrao" | "tv";
}


export function AvisoSemCoi({ variante = "padrao" }: AvisoSemCoiProps) {
  const sessao = useSessaoOpcional();
  if (!sessao?.temModulo("TRANSFERENCIAS")) return null;
  return <ConteudoAvisoSemCoi variante={variante} />;
}

function ConteudoAvisoSemCoi({ variante }: Required<AvisoSemCoiProps>) {
  const [rodada, setRodada] = useState(0);
  const { data } = useAsync((s) => getTransferenciasSemCoi(s), [], rodada);


  useEffect(() => {
    const proxima = () => setRodada((r) => r + 1);
    const timer = setInterval(() => {
      if (!document.hidden) proxima();
    }, INTERVALO_AVISO_COI_MS);
    const aoMudarVisibilidade = () => {
      if (!document.hidden) proxima();
    };
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    };
  }, []);


  if (!data || data.total === 0) return null;

  const tv = variante === "tv";
  const plural = data.total !== 1;
  const restantes = data.total - data.itens.length;

  return (
    <section
      role="alert"
      aria-label="Transferências com COI errado"
      className={`flex flex-col gap-3 sm:flex-row sm:items-center ${
        tv
          ? "rounded-lg border-2 border-critico bg-critico/15 px-[2vw] py-[2vh] shadow-[0_0_24px_rgb(208_59_59/0.35)]"
          : "rounded-painel border border-critico/40 bg-critico/[0.05] p-4 sm:px-5"
      }`}
    >
      <Siren aria-hidden className={`shrink-0 text-critico-texto ${tv ? "size-[clamp(2.5rem,6vh,4rem)] animate-pulse" : "size-6 self-start sm:self-center"}`} />
      <div className="min-w-0 flex-1">
        <p className={`font-display text-critico-texto ${tv ? "font-extrabold uppercase tracking-wide text-[clamp(1.25rem,3.4vh,2.25rem)]" : "text-base font-bold"}`}>
          {formatarNumero(data.total)} {plural ? "transferências" : "transferência"} com COI errado
        </p>
        <p className={`text-texto ${tv ? "text-[clamp(0.9rem,2vh,1.3rem)]" : "text-sm"}`}>
          A nota de saída ou de entrada usou o código de operação interna errado: {plural ? "foram feitas" : "foi feita"}{" "}
          errada{plural ? "s" : ""} no ERP. Confira e corrija.
        </p>
        <ul className={`mt-2 flex flex-wrap gap-2 ${tv ? "text-[clamp(0.85rem,1.8vh,1.2rem)]" : "text-xs"}`}>
          {data.itens.map((t) => {
            const numero = t.numero_nota ? `NF ${t.numero_nota}` : t.id_erp;
            const texto = `${numero} · ${t.empresa_origem.codigo} → ${t.empresa_destino?.codigo ?? "?"}`;
            return (
              <li key={t.id}>
                {tv ? (
                  <span className="rounded-full bg-critico/30 px-3 py-1 font-semibold text-texto">{texto}</span>
                ) : (
                  <Link
                    to={`${ROTA_SEM_COI}&detalhe=${t.id}`}
                    onClick={irParaSemCoi(`${ROTA_SEM_COI}&detalhe=${t.id}`)}
                    className="tabular inline-block rounded border border-critico/30 bg-superficie px-2 py-0.5 font-medium text-critico-texto transition-colors hover:border-critico/60 hover:bg-critico/[0.06]"
                  >
                    {texto}
                  </Link>
                )}
              </li>
            );
          })}
          {restantes > 0 && <li className="px-1 py-0.5 text-texto-2">e mais {formatarNumero(restantes)}</li>}
        </ul>
      </div>
      {!tv && (
        <Link to={ROTA_SEM_COI} onClick={irParaSemCoi(ROTA_SEM_COI)} className="btn shrink-0 bg-critico text-white hover:bg-critico-texto active:translate-y-px">
          Ver transferências
          <ArrowRight aria-hidden className="size-4" />
        </Link>
      )}
    </section>
  );
}
