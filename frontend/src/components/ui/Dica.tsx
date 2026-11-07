import { Info } from "lucide-react";
import { useEffect, useId, useState } from "react";

interface DicaProps {

  texto: string;

  sobre: string;
}


export function Dica({ texto, sobre }: DicaProps) {
  const id = useId();
  const [aberta, setAberta] = useState(false);

  useEffect(() => {
    if (!aberta) return;
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberta(false);
    };
    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, [aberta]);

  return (
    <span className="relative inline-flex" onMouseEnter={() => setAberta(true)} onMouseLeave={() => setAberta(false)}>
      <button
        type="button"
        aria-label={`Sobre: ${sobre}`}
        aria-describedby={id}
        onFocus={() => setAberta(true)}
        onBlur={() => setAberta(false)}
        onClick={() => setAberta((a) => !a)}
        className="grid size-6 place-items-center rounded-full text-texto-mudo hover:text-texto"
      >
        <Info aria-hidden className="size-3.5" />
      </button>
      <span
        id={id}
        role="tooltip"
        hidden={!aberta}
        className="absolute right-0 top-full z-20 mt-1.5 w-60 rounded-lg border border-borda-forte bg-superficie-3 px-3 py-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-texto-2 shadow-elevado"
      >
        {texto}
      </span>
    </span>
  );
}
