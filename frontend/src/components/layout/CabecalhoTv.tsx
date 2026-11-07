import { Expand, LogOut, Shrink } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { MARCA } from "../../lib/marca";
import { formatarHora, formatarHoraMinuto } from "../../lib/format";

interface CabecalhoTvProps {

  titulo: ReactNode;
  escopo: string;
  atualizadoEm: Date | null;

  saida: string;
}


export function CabecalhoTv({ titulo, escopo, atualizadoEm, saida }: CabecalhoTvProps) {
  const agora = useRelogio();
  const telaCheia = useTelaCheia();

  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-4">
        <div className="leading-tight">
          <h1 className="marca text-[clamp(1.5rem,3.2vh,2.5rem)]">
            {MARCA.partes[0]} <span className="text-acento">{MARCA.partes[1]}</span> · {titulo}
          </h1>
          <p className="marca-apoio text-[clamp(0.75rem,1.6vh,1.1rem)] text-texto-2">{escopo}</p>
        </div>
      </div>
      <div className="flex items-center gap-5">
        <div className="text-right leading-tight">
          <p className="tabular font-display text-[clamp(2rem,6vh,4rem)] font-bold">{formatarHoraMinuto(agora)}</p>
          <p className="text-[clamp(0.7rem,1.4vh,1rem)] text-texto-mudo" aria-live="polite">
            {atualizadoEm ? `Atualizado às ${formatarHora(atualizadoEm)}` : "Carregando…"}
            {" · a cada minuto"}
          </p>
        </div>
        <div className="flex flex-col gap-2">
          {telaCheia.suportado && (
            <button type="button" onClick={telaCheia.alternar} className="btn btn-sm btn-secundario">
              {telaCheia.ativa ? <Shrink aria-hidden className="size-3.5" /> : <Expand aria-hidden className="size-3.5" />}
              {telaCheia.ativa ? "Sair da tela cheia" : "Tela cheia"}
            </button>
          )}
          <Link to={saida} className="btn btn-sm btn-fantasma">
            <LogOut aria-hidden className="size-3.5" />
            Sair do modo TV
          </Link>
        </div>
      </div>
    </header>
  );
}


function useRelogio(): Date {
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setAgora(new Date()), 15_000);
    return () => clearInterval(timer);
  }, []);
  return agora;
}

function useTelaCheia() {
  const suportado = typeof document !== "undefined" && Boolean(document.documentElement.requestFullscreen);
  const [ativa, setAtiva] = useState(() => typeof document !== "undefined" && Boolean(document.fullscreenElement));

  useEffect(() => {
    const aoMudar = () => setAtiva(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", aoMudar);
    return () => document.removeEventListener("fullscreenchange", aoMudar);
  }, []);

  const alternar = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen().catch(() => {});
  }, []);

  return { suportado, ativa, alternar };
}
