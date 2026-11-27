type Props = {
  frase: string;
  causa: string;
};

/** Bloco neutro de bloqueio: fio lateral, sem cor de erro, sem `role="alert"` e sem ícone.
 *  É o mesmo desenho usado pelas recusas do assistente — um só lugar para a marcação. */
export function EstadoBloqueio({ frase, causa }: Props) {
  return (
    <div className="recusa">
      <p className="recusa__frase">{frase}</p>
      <p className="recusa__causa texto-menor secundario">{causa}</p>
    </div>
  );
}

/** Causa em linguagem de estudante. A categoria **nunca** entra no texto: é enum, não copy. */
export function causaDoBloqueio(categoria: string | undefined, sujeito: "pergunta" | "pedido"): string {
  const injecao = categoria === "INJECTION" || categoria === "PROMPT_INJECTION";
  const barreira = injecao ? "pela barreira de prompt injection" : "por uma barreira de segurança";

  return sujeito === "pergunta"
    ? `A pergunta foi bloqueada ${barreira}, antes de qualquer busca nos artigos.`
    : `O pedido foi bloqueado ${barreira}, antes de qualquer chamada ao servidor.`;
}
