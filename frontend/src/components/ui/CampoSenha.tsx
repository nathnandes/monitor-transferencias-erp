import { Eye, EyeOff } from "lucide-react";
import { useState, type InputHTMLAttributes } from "react";

type CampoSenhaProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { id: string };


export function CampoSenha({ id, disabled, className, ...props }: CampoSenhaProps) {
  const [visivel, setVisivel] = useState(false);
  if (disabled && visivel) setVisivel(false);

  return (
    <div className="relative">
      <input
        {...props}
        id={id}
        type={visivel ? "text" : "password"}
        disabled={disabled}
        className={`campo pr-10 ${className ?? ""}`}
      />
      <button
        type="button"
        onClick={() => setVisivel((v) => !v)}

        onMouseDown={(e) => e.preventDefault()}
        disabled={disabled}
        aria-label={visivel ? "Ocultar senha" : "Mostrar senha"}
        aria-pressed={visivel}
        aria-controls={id}
        className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-lg text-texto-mudo outline-none transition-colors hover:text-acento-texto focus-visible:text-acento-texto focus-visible:ring-2 focus-visible:ring-acento/40 disabled:pointer-events-none disabled:opacity-60"
      >
        {visivel ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
      </button>
    </div>
  );
}
