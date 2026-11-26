type Props = {
  /** Quem recusou. O porteiro barra antes de qualquer LLM; o modelo recusa depois de ler os trechos;
   *  o guardrail barra a pergunta antes de tudo, por política. */
  motivo: "porteiro" | "modelo" | "guardrail";
  frase: string;
  /** Categoria do veredito, quando o bloqueio veio de um guardrail. */
  categoria?: string;
};

const CAUSA_PORTEIRO =
  "A pergunta ficou fora dos temas dos 20 artigos: a busca parou antes de qualquer chamada ao modelo.";
const CAUSA_MODELO =
  "A busca encontrou trechos, mas o modelo não achou neles base suficiente para responder.";

/** O texto acompanha a categoria: uma barreira futura não é descrita como injeção. */
function causa(motivo: Props["motivo"], categoria?: string): string {
  if (motivo === "porteiro") return CAUSA_PORTEIRO;
  if (motivo === "modelo") return CAUSA_MODELO;
  if (categoria === "INJECTION" || categoria === "PROMPT_INJECTION") {
    return "A pergunta foi bloqueada pela barreira de prompt injection, antes de qualquer busca nos artigos.";
  }
  // A categoria fica nos detalhes técnicos; aqui o texto é para o estudante.
  return "A pergunta foi bloqueada por uma barreira de segurança, antes de qualquer busca nos artigos.";
}

/** Recusa não é erro: tom neutro, fio lateral, sem cor de falha e sem ícone. */
export function EstadoRecusa({ motivo, frase, categoria }: Props) {
  return (
    <div className="recusa">
      <p className="recusa__frase">{frase}</p>
      <p className="recusa__causa texto-menor secundario">{causa(motivo, categoria)}</p>
    </div>
  );
}
