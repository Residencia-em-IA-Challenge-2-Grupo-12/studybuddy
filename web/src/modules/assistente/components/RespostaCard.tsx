"use client";

import { useEffect, useId, useRef } from "react";

import type { Resposta } from "../types";
import { bloqueou } from "../veredito";
import { DetalhesTecnicos } from "./DetalhesTecnicos";
import { EstadoRecusa } from "./EstadoRecusa";
import { FontesList } from "./FontesList";
import { MetadadoResposta } from "./MetadadoResposta";

/** `verificacao.citadas` traz IDs (`artigo_05`); `fontes` traz os nomes completos. */
function resolverFonte(id: string, fontes: string[]): string {
  return fontes.find((nome) => nome === id || nome.startsWith(`${id}_`)) ?? id;
}

type Props = {
  resposta: Resposta;
};

export function RespostaCard({ resposta }: Props) {
  const idTitulo = useId();
  const titulo = useRef<HTMLHeadingElement>(null);

  // Cada resposta nova leva o foco ao título: quem usa leitor de tela ou teclado sabe onde o resultado começa.
  useEffect(() => {
    titulo.current?.focus();
  }, [resposta]);

  const peloPorteiro = resposta.barrada_pelo_porteiro;
  const peloModelo = resposta.verificacao?.recusa === true;
  const peloGuardrail = bloqueou(resposta.veredito);
  const recusada = peloPorteiro || peloModelo || peloGuardrail;
  const verificacao = resposta.verificacao;
  const removidas = verificacao?.fora_do_contexto ?? [];

  return (
    <article className="resultado" aria-labelledby={idTitulo}>
      <h2 className="resultado__titulo" id={idTitulo} ref={titulo} tabIndex={-1}>
        {peloGuardrail ? "Pedido bloqueado" : recusada ? "Sem base para responder" : "Resposta"}
      </h2>

      <MetadadoResposta pipeline={resposta.pipeline} latencia_s={resposta.latencia_s} />

      {recusada ? (
        <EstadoRecusa
          motivo={peloGuardrail ? "guardrail" : peloPorteiro ? "porteiro" : "modelo"}
          frase={resposta.resposta}
          categoria={peloGuardrail ? resposta.veredito?.categoria : undefined}
        />
      ) : (
        <>
          {/* Texto puro: as citações [Fonte: ...] ficam onde o modelo as colocou. */}
          <p className="prosa resultado__texto">{resposta.resposta}</p>

          {verificacao?.citadas?.length ? (
            <section className="citadas" aria-labelledby={`${idTitulo}-citadas`}>
              <h3 id={`${idTitulo}-citadas`}>Citações verificadas</h3>
              <ul className="citadas__lista">
                {verificacao.citadas.map((id) => (
                  <li key={id}>{resolverFonte(id, resposta.fontes)}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {verificacao?.sem_citacao ? (
            <p className="texto-menor aviso">
              O modelo não citou a fonte. Os trechos consultados estão listados abaixo.
            </p>
          ) : null}

          {removidas.length > 0 ? (
            <p className="texto-menor aviso">
              Citação removida por não estar entre os trechos consultados: {removidas.join(", ")}.
            </p>
          ) : null}
        </>
      )}

      {/* Recusa também mostra o que foi consultado, e sempre o metadado. */}
      <FontesList fontes={resposta.fontes} />

      <DetalhesTecnicos resposta={resposta} />
    </article>
  );
}
