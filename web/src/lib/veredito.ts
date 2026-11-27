/** Resultado da barreira de guardrails. Dois formatos convivem hoje:
 *  - o do `guardrails/injection.py` (`categoria: "INJECTION"`, `motivos`), que o serviço já devolve;
 *  - o canônico do Maestro (`agentes/contratos.py`: `permitido`, `resposta_bloqueio` e as categorias
 *    `PROMPT_INJECTION`, `HATE_SPEECH`, `MEDICAL_ADVICE`, `OUT_OF_SCOPE`), que a `clinico.py` já usa.
 *  A tela bloqueia por `permitido === false`, e por default-deny em qualquer categoria diferente de "OK". */
export type Veredito = {
  permitido?: boolean;
  categoria?: "OK" | "INJECTION" | "PROMPT_INJECTION" | "HATE_SPEECH" | "MEDICAL_ADVICE" | "OUT_OF_SCOPE" | (string & {});
  motivos?: string[];
  resposta_bloqueio?: string | null;
};

/** O guardrail barrou o pedido?
 *
 *  Default-deny deliberado: o contrato de guardrails ainda vai mudar (o canônico do Maestro já usa
 *  `permitido` e categorias novas como `MEDICAL_ADVICE`). Se a tela só reconhecesse "INJECTION",
 *  uma categoria nova cairia como resposta normal. Aqui, qualquer coisa diferente de "OK" bloqueia. */
export function bloqueou(veredito: Veredito | null | undefined): boolean {
  if (!veredito) return false;
  if (typeof veredito.permitido === "boolean") return !veredito.permitido;
  return Boolean(veredito.categoria && veredito.categoria !== "OK");
}

/** Erro de fluxo quando a barreira barrou o pedido. Não é falha de sistema: a tela apresenta como
 *  bloqueio neutro, com a mensagem fixa, e não como alerta de erro. */
export class BloqueioError extends Error {
  readonly categoria?: string;
  readonly motivos: string[];
  readonly mensagem: string;

  constructor(veredito: Veredito, mensagem: string) {
    super(mensagem);
    this.name = "BloqueioError";
    this.categoria = veredito.categoria;
    this.motivos = veredito.motivos ?? [];
    this.mensagem = mensagem;
  }
}

const FRASE_PADRAO = "Não consigo ajudar com esse pedido.";

/** Lança `BloqueioError` quando o payload traz um veredito que barra. Fica na borda do serviço:
 *  dali para dentro, o dado só circula se passou pela barreira. A mensagem fixa pode vir na raiz do
 *  payload (como em `service.py`) ou dentro do veredito (contrato canônico). */
export function exigirPermitido<T>(payload: T): T {
  const corpo = payload as { veredito?: Veredito | null; resposta_bloqueio?: string | null } | null;
  if (!corpo || !bloqueou(corpo.veredito)) return payload;

  const veredito = corpo.veredito as Veredito;
  throw new BloqueioError(veredito, corpo.resposta_bloqueio ?? veredito.resposta_bloqueio ?? FRASE_PADRAO);
}
