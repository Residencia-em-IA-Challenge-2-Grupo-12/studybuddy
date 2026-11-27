import { EstadoBloqueio, causaDoBloqueio } from "@/modules/fluxo/components/EstadoBloqueio";

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

/** Recusa não é erro: tom neutro, fio lateral, sem cor de falha e sem ícone. */
export function EstadoRecusa({ motivo, frase, categoria }: Props) {
  const causa =
    motivo === "porteiro"
      ? CAUSA_PORTEIRO
      : motivo === "modelo"
        ? CAUSA_MODELO
        : causaDoBloqueio(categoria, "pergunta");

  return <EstadoBloqueio frase={frase} causa={causa} />;
}
