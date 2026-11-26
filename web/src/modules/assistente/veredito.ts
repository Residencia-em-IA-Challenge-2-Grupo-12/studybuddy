import type { Veredito } from "./types";

/** O guardrail barrou a pergunta?
 *
 *  Default-deny deliberado: o contrato de guardrails ainda vai mudar (o canônico do Maestro já usa
 *  `permitido` e categorias novas como `MEDICAL_ADVICE`). Se a tela só reconhecesse "INJECTION",
 *  uma categoria nova cairia como resposta normal. Aqui, qualquer coisa diferente de "OK" bloqueia. */
export function bloqueou(veredito: Veredito | null | undefined): boolean {
  if (!veredito) return false;
  if (typeof veredito.permitido === "boolean") return !veredito.permitido;
  return Boolean(veredito.categoria && veredito.categoria !== "OK");
}
