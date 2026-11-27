import type { ReactNode } from "react";

/** Renderizador mínimo de markdown, sem dependência e sem `dangerouslySetInnerHTML`.
 *  Cobre o que `MensagemFinal.markdown` usa hoje: parágrafos, listas com "- " e, na linha,
 *  negrito e link. */
const TOKEN = /(\*\*([^*]+)\*\*)|(\[([^\]]+)\]\(([^)]+)\))/g;

function emLinha(texto: string): ReactNode[] {
  const nos: ReactNode[] = [];
  let ultimo = 0;

  for (const achado of texto.matchAll(TOKEN)) {
    const inicio = achado.index ?? 0;
    if (inicio > ultimo) nos.push(texto.slice(ultimo, inicio));

    if (achado[2]) {
      nos.push(<strong key={inicio}>{achado[2]}</strong>);
    } else if (achado[4]) {
      nos.push(
        <a key={inicio} href={achado[5]} target="_blank" rel="noreferrer">
          {achado[4]}
        </a>,
      );
    }
    ultimo = inicio + achado[0].length;
  }

  if (ultimo < texto.length) nos.push(texto.slice(ultimo));
  return nos;
}

export function Markdown({ texto }: { texto: string }) {
  const blocos = texto.split(/\n{2,}/).filter((bloco) => bloco.trim() !== "");

  return (
    <>
      {blocos.map((bloco, indice) => {
        const linhas = bloco.split("\n").filter((linha) => linha.trim() !== "");
        const ehLista = linhas.every((linha) => linha.startsWith("- "));

        if (ehLista) {
          return (
            <ul key={indice} className="mensagem__lista">
              {linhas.map((linha, posicao) => (
                <li key={posicao}>{emLinha(linha.slice(2))}</li>
              ))}
            </ul>
          );
        }

        return <p key={indice}>{emLinha(linhas.join(" "))}</p>;
      })}
    </>
  );
}
