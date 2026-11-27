import type { Pipeline } from "../types";

type Props = {
  pipeline: Pipeline;
  latencia_s: number;
};

const NOMES: Record<Pipeline, string> = {
  classico: "clássico",
  agentes: "multiagente",
};

/** Metadado como texto tipográfico: hierarquia por peso e cor, sem cápsula, sem borda, sem ícone. */
export function MetadadoResposta({ pipeline, latencia_s }: Props) {
  const segundos = latencia_s.toFixed(1).replace(".", ",");

  return (
    <p className="resultado__meta texto-menor secundario">
      pipeline <span className="resultado__pipeline">{NOMES[pipeline]}</span>
      {" · "}
      {segundos} s
    </p>
  );
}
