"use client";

import { useId, useRef } from "react";

type Opcao<T extends string | number> = { valor: T; rotulo: string };

type Props<T extends string | number> = {
  rotulo: string;
  valor: T | null;
  opcoes: Opcao<T>[];
  aoMudar: (valor: T) => void;
  /** Explica a escala: "1 = muito baixo, 5 = muito alto". */
  ajuda?: string;
};

/** Radiogroup com seleção única: setas mudam o valor e o foco acompanha. Serve para escolha de
 *  texto (cronotipo) e para escala numérica (check-in). */
export function EscolhaUnica<T extends string | number>({ rotulo, valor, opcoes, aoMudar, ajuda }: Props<T>) {
  const id = useId();
  const botoes = useRef<(HTMLButtonElement | null)[]>([]);

  function aoTeclar(evento: React.KeyboardEvent<HTMLButtonElement>, indice: number) {
    const passo =
      evento.key === "ArrowRight" || evento.key === "ArrowDown"
        ? 1
        : evento.key === "ArrowLeft" || evento.key === "ArrowUp"
          ? -1
          : 0;
    if (passo === 0) return;

    evento.preventDefault();
    const proximo = (indice + passo + opcoes.length) % opcoes.length;
    aoMudar(opcoes[proximo].valor);
    botoes.current[proximo]?.focus();
  }

  return (
    <div className="escolha">
      <span className="campo__rotulo" id={id}>
        {rotulo}
      </span>
      <div className="segmentado" role="radiogroup" aria-labelledby={id}>
        {opcoes.map((opcao, indice) => {
          const ativa = opcao.valor === valor;
          // Sem escolha ainda, o primeiro item recebe o Tab — senão o grupo fica inalcançável.
          const tabulavel = valor === null ? indice === 0 : ativa;
          return (
            <button
              key={opcao.valor}
              ref={(elemento) => {
                botoes.current[indice] = elemento;
              }}
              type="button"
              role="radio"
              aria-checked={ativa}
              tabIndex={tabulavel ? 0 : -1}
              className="segmentado__opcao"
              onClick={() => aoMudar(opcao.valor)}
              onKeyDown={(evento) => aoTeclar(evento, indice)}
            >
              {opcao.rotulo}
            </button>
          );
        })}
      </div>
      {ajuda ? <p className="texto-menor secundario">{ajuda}</p> : null}
    </div>
  );
}
