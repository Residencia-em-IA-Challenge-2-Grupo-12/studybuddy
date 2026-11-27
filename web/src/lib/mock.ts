/** Transporte mock: responde por caminho, com os dados das fixtures da [0.2].
 *
 *  A superfície `/fluxo/*` é **provisória** — não existe rota no backend. Quando o Maestro expuser as
 *  dele, estes caminhos são reconciliados e o mock passa a ser só um cenário de desenvolvimento. */

import { CONTEXTO, PROPOSTA, RESULTADO } from "@/mocks";

import type { Cronotipo, PlanoResposta } from "@/modules/fluxo/types";

/** Chave: "MÉTODO /caminho", igual ao que `api()` recebe. A função recebe o corpo já decodificado. */
export const ROTAS_MOCK: Record<string, (corpo?: Record<string, unknown>) => unknown> = {
  // As três fixtures de cronotipo existem: o mock devolve a que combina com a escolha.
  "POST /fluxo/contexto": (corpo) => {
    const cronotipo = corpo?.cronotipo as Cronotipo | undefined;
    return (cronotipo && CONTEXTO[cronotipo]) || CONTEXTO.matutino;
  },
  // Check-in e materiais ecoam o que a tela enviou: quem normaliza é o backend, não a tela.
  "POST /fluxo/checkin": (corpo) => corpo ?? CONTEXTO.matutino.checkin,
  "POST /fluxo/materiais": (corpo) =>
    Array.isArray(corpo?.materiais) ? corpo.materiais : CONTEXTO.matutino.materiais,
  "POST /fluxo/plano": (): PlanoResposta => ({
    proposta: PROPOSTA.valida,
    validacao: RESULTADO.aprovado,
  }),
  "POST /fluxo/confirmar": () => ({ sincronizado: true }),
};

function corpoDecodificado(corpo: BodyInit | null | undefined): Record<string, unknown> | undefined {
  if (typeof corpo !== "string") return undefined;
  try {
    const dados = JSON.parse(corpo);
    return typeof dados === "object" && dados !== null ? (dados as Record<string, unknown>) : undefined;
  } catch {
    return undefined;
  }
}

export function respostaMock(
  metodo: string,
  caminho: string,
  corpo?: BodyInit | null,
): { encontrada: boolean; corpo?: unknown } {
  const rota = ROTAS_MOCK[`${metodo.toUpperCase()} ${caminho}`];
  if (!rota) return { encontrada: false };
  return { encontrada: true, corpo: rota(corpoDecodificado(corpo)) };
}
