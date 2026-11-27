"use client";

import { useId, useRef } from "react";

import type { Pipeline } from "../types";

const OPCOES: { valor: Pipeline; rotulo: string }[] = [
  { valor: "classico", rotulo: "Clássico" },
  { valor: "agentes", rotulo: "Multiagente" },
];

type Props = {
  valor: Pipeline;
  aoMudar: (pipeline: Pipeline) => void;
};

/** Um controle segmentado (não dois botões soltos): radiogroup com seleção única, setas mudam o modo. */
export function PipelineToggle({ valor, aoMudar }: Props) {
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
    const proximo = (indice + passo + OPCOES.length) % OPCOES.length;
    aoMudar(OPCOES[proximo].valor);
    botoes.current[proximo]?.focus();
  }

  return (
    <div className="modo">
      <span className="modo__rotulo" id={id}>
        Modo
      </span>
      <div className="segmentado" role="radiogroup" aria-labelledby={id}>
        {OPCOES.map((opcao, indice) => {
          const ativo = opcao.valor === valor;
          return (
            <button
              key={opcao.valor}
              ref={(elemento) => {
                botoes.current[indice] = elemento;
              }}
              type="button"
              role="radio"
              aria-checked={ativo}
              tabIndex={ativo ? 0 : -1}
              className="segmentado__opcao"
              onClick={() => aoMudar(opcao.valor)}
              onKeyDown={(evento) => aoTeclar(evento, indice)}
            >
              {opcao.rotulo}
            </button>
          );
        })}
      </div>
    </div>
  );
}
