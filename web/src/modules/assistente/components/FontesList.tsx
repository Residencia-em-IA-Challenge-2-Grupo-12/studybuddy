"use client";

import { useId } from "react";

type Props = {
  fontes: string[];
};

/** Os arquivos consultados, pelo nome. Nomes longos quebram linha em vez de estourar a coluna. */
export function FontesList({ fontes }: Props) {
  const id = useId();

  return (
    <section className="fontes" aria-labelledby={id}>
      <h3 id={id}>Fontes consultadas</h3>
      {fontes.length === 0 ? (
        <p className="texto-menor secundario">Nenhuma fonte consultada.</p>
      ) : (
        <ul className="fontes__lista">
          {fontes.map((nome) => (
            <li key={nome}>{nome}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
