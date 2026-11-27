/** Contratos do fluxo de estudo, espelhando api/app/modules/agentes/contratos.py.
 *  Datas e horas são strings ISO ("2026-11-30", "08:30") — o mesmo que o JSON carrega. */

export type Cronotipo = "matutino" | "vespertino" | "noturno";
export type CargaCognitiva = "alta" | "baixa";
export type Regra = "CONFLITO_AGENDA" | "INTEGRIDADE_CIRCADIANA" | "SOBRECARGA";

/** [inicio, fim) num dia. */
export type Janela = {
  dia: string;
  inicio: string;
  fim: string;
};

export type CheckIn = {
  energia: number; // 1..5
  horas_sono: number; // 0..24
  estresse: number; // 1..5
};

export type Material = {
  id: string;
  disciplina: string;
  titulo: string;
  carga: CargaCognitiva;
  horas_estimadas: number;
  dificuldade: number; // 1..5
  prazo: string | null;
};

export type ContextoEstudante = {
  estudante_id: string;
  cronotipo: Cronotipo;
  semana_inicio: string;
  livres: Janela[];
  ocupados: Janela[];
  picos: Janela[];
  vales: Janela[];
  sono: Janela[];
  refeicoes: Janela[];
  materiais: Material[];
  checkin: CheckIn;
  indice_capacidade: number; // 0..1
};

export type BlocoEstudo = {
  id: string;
  dia: string;
  inicio: string;
  fim: string;
  disciplina: string;
  material_id: string;
  carga: CargaCognitiva;
  tecnica: string;
  foco_min: number;
  pausa_min: number;
  justificativa?: string;
  fontes?: string[];
};

export type PropostaGrade = {
  estudante_id: string;
  semana_inicio: string;
  modo: "normal" | "reducao_danos";
  blocos: BlocoEstudo[];
  fora_da_grade: string[];
  iteracao: number;
};

export type Violacao = {
  regra: Regra;
  dia: string;
  bloco_id: string | null;
  mensagem: string;
  excesso_min?: number | null;
};

export type ResultadoValidacao = {
  status: "APROVADO" | "REPROVADO";
  violacoes: Violacao[];
};

export type MensagemFinal = {
  markdown: string;
  tom: string;
  links: string[];
};

/** O que o onboarding coleta. Só horários, sem datas: o Research é quem distribui pelos dias da
 *  semana e quebra a janela na meia-noite (o contrato não deixa uma `Janela` cruzar o dia).
 *  `picos`, `vales`, `ocupados` e `indice_capacidade` também são derivados lá. */
export type EntradaOnboarding = {
  cronotipo: Cronotipo;
  sono: { inicio: string; fim: string };
  refeicoes: { cafe: string; almoco: string; jantar: string };
  agendaConectada: boolean;
};

/** As quatro escalas que a issue pede. O contrato `CheckIn` carrega só três campos (energia,
 *  horas de sono e estresse); humor e qualidade do sono ficam no cliente até o épico 0 decidir
 *  se entram lá. A conversão está em `modules/checkin/mapeamento.ts`, com a regra explícita. */
export type EscalasCheckIn = {
  humor: number; // 1..5
  estresse: number; // 1..5
  sono: number; // 1..5 (qualidade)
  fadiga: number; // 1..5
};

/** Resposta do passo do plano. `mensagem` é opcional porque a [0.2] não tem fixture de
 *  `MensagemFinal`; enquanto não houver, o mock devolve só proposta e validação. */
export type PlanoResposta = {
  proposta: PropostaGrade;
  validacao: ResultadoValidacao;
  mensagem?: MensagemFinal;
};
