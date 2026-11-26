"use client";

import { useEffect, useState } from "react";

const MAXIMO = 1000;
const MINIMO = 3; // o mesmo mínimo de PerguntaIn (schemas.py:12)

type Props = {
  carregando: boolean;
  aoEnviar: (pergunta: string) => void;
  aoCancelar: () => void;
};

export function PerguntaForm({ carregando, aoEnviar, aoCancelar }: Props) {
  const [texto, setTexto] = useState("");
  const [segundos, setSegundos] = useState(0);

  // Cronômetro só enquanto espera: a latência local pode chegar a minutos.
  useEffect(() => {
    if (!carregando) {
      setSegundos(0);
      return;
    }
    const inicio = performance.now();
    const id = window.setInterval(() => setSegundos((performance.now() - inicio) / 1000), 100);
    return () => window.clearInterval(id);
  }, [carregando]);

  const pronto = texto.trim().length >= MINIMO;

  function enviar() {
    const pergunta = texto.trim();
    if (carregando || pergunta.length < MINIMO) return;
    aoEnviar(pergunta);
  }

  function aoTeclar(evento: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (evento.key !== "Enter") return;
    if (evento.nativeEvent.isComposing) return; // Enter de IME fecha a composição; não é envio
    if (evento.shiftKey && !evento.metaKey && !evento.ctrlKey) return; // Shift+Enter quebra a linha
    evento.preventDefault();
    enviar();
  }

  return (
    <form
      className="pergunta"
      onSubmit={(evento) => {
        evento.preventDefault();
        enviar();
      }}
    >
      <div className="pergunta__topo">
        <label className="pergunta__rotulo" htmlFor="pergunta">
          Sua pergunta
        </label>
        <span className="pergunta__contador secundario" id="contador-pergunta">
          {texto.length}/{MAXIMO}
        </span>
      </div>

      <textarea
        id="pergunta"
        className="pergunta__campo"
        value={texto}
        onChange={(evento) => setTexto(evento.target.value)}
        onKeyDown={aoTeclar}
        maxLength={MAXIMO}
        rows={4}
        aria-describedby="contador-pergunta dica-pergunta"
        placeholder="Ex.: trabalho 8 horas por dia e tenho 2 horas livres à noite. Como encaixo o estudo?"
      />

      <div className="pergunta__acoes">
        <p className="pergunta__dica texto-menor secundario" id="dica-pergunta">
          Enter envia · Shift+Enter quebra a linha
        </p>
        <div className="pergunta__botoes">
          {carregando && (
            <span className="pergunta__tempo texto-menor secundario">
              {segundos.toFixed(1).replace(".", ",")} s
            </span>
          )}
          {carregando ? (
            <button type="button" className="botao botao--secundario" onClick={aoCancelar}>
              Cancelar
            </button>
          ) : (
            <button type="submit" className="botao botao--principal" disabled={!pronto}>
              Perguntar
            </button>
          )}
        </div>
      </div>
    </form>
  );
}
