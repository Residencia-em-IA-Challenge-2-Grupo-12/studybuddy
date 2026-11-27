/** Transporte mock: responde por caminho, com os dados das fixtures da [0.2].
 *
 *  A superfície `/fluxo/*` é **provisória** — não existe rota no backend. Quando o Maestro expuser as
 *  dele, estes caminhos são reconciliados e o mock passa a ser só um cenário de desenvolvimento. */

import { CONTEXTO, PROPOSTA, RESULTADO } from "@/mocks";

import type { Cronotipo, MensagemFinal, PlanoResposta } from "@/modules/fluxo/types";

/** A [0.2] não tem fixture de `MensagemFinal`, então este texto é **sintético**: escrito aqui, no
 *  mock, para a tela do plano ter o que renderizar. Quando a fixture existir, o mock devolve a dela. */
export const MENSAGEM_SINTETICA: MensagemFinal = {
  markdown: [
    `Montei sua semana com **${PROPOSTA.valida.blocos.length} blocos** de foco, dentro dos horários que você informou.`,
    "",
    "- Os blocos longos ficam nos seus picos de energia.",
    "- As pausas são curtas e fixas, para não virarem tempo morto.",
    "",
    "Se um dia não couber, ajuste o bloco em vez de esticar a noite.",
  ].join("\n"),
  tom: "direto",
  links: [],
};

/** Cenários de plano. As fixtures da [0.2] **não emparelham por nome**: `resultado/sobrecarga.json`
 *  aponta para 2026-12-02, que só existe em `proposta/sobrecarga_noturna.json`. O pareamento abaixo é
 *  por coerência de datas, não por nome de arquivo.
 *  A escolha vem de `localStorage["studybuddy.cenario"]` (padrão `valida`), para os testes e para
 *  conferir os estados sem um seletor na tela. */
const CENARIOS: Record<string, () => PlanoResposta> = {
  valida: () => ({ proposta: PROPOSTA.valida, validacao: RESULTADO.aprovado, mensagem: MENSAGEM_SINTETICA }),
  reprovado: () => ({ proposta: PROPOSTA.violacoes, validacao: RESULTADO.reprovado, mensagem: MENSAGEM_SINTETICA }),
  reducao_danos: () => ({
    proposta: PROPOSTA.reducao_danos,
    validacao: RESULTADO.aprovado,
    mensagem: MENSAGEM_SINTETICA,
  }),
  sobrecarga: () => ({
    proposta: PROPOSTA.sobrecarga_noturna,
    validacao: RESULTADO.sobrecarga,
    mensagem: MENSAGEM_SINTETICA,
  }),
};

function cenarioAtual(): string {
  if (typeof window === "undefined") return "valida";
  try {
    return window.localStorage.getItem("studybuddy.cenario") ?? "valida";
  } catch {
    return "valida";
  }
}

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
  "POST /fluxo/plano": () => (CENARIOS[cenarioAtual()] ?? CENARIOS.valida)(),
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
