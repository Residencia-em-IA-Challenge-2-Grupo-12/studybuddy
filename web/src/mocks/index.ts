// GERADO por scripts/sincronizar-mocks.mjs — não editar à mão.
// Fonte: api/tests/fixtures (contratos da [0.2]) e pesquisa/fixtures/communication.
//
// O `as Tipo` é ponte, não check: o TypeScript infere JSON como `string` e perde as uniões
// (`modo: "normal" | "reducao_danos"`, `status: "APROVADO" | "REPROVADO"`). Quem confere o mock
// contra o contrato é scripts/validar-mocks.py, que roda o pydantic de verdade.

import type { ContextoEstudante, PropostaGrade, ResultadoValidacao } from "@/modules/fluxo/types";

import agenda_cheia from "./contexto/agenda_cheia.json";
import alta_energia from "./contexto/alta_energia.json";
import fadiga from "./contexto/fadiga.json";
import matutino from "./contexto/matutino.json";
import noturno from "./contexto/noturno.json";
import prazo_apertado from "./contexto/prazo_apertado.json";
import vespertino from "./contexto/vespertino.json";
import higiene_sono from "./proposta/higiene_sono.json";
import reducao_danos from "./proposta/reducao_danos.json";
import refeicao from "./proposta/refeicao.json";
import sobrecarga_fadiga from "./proposta/sobrecarga_fadiga.json";
import sobrecarga_noturna from "./proposta/sobrecarga_noturna.json";
import valida from "./proposta/valida.json";
import violacoes from "./proposta/violacoes.json";
import aprovado from "./resultado/aprovado.json";
import reprovado from "./resultado/reprovado.json";
import sobrecarga from "./resultado/sobrecarga.json";
import checkins from "./communication/checkins.json";
import evidencias from "./communication/evidencias.json";
import grade from "./communication/grade.json";

export const CONTEXTO = {
  agenda_cheia: agenda_cheia as ContextoEstudante,
  alta_energia: alta_energia as ContextoEstudante,
  fadiga: fadiga as ContextoEstudante,
  matutino: matutino as ContextoEstudante,
  noturno: noturno as ContextoEstudante,
  prazo_apertado: prazo_apertado as ContextoEstudante,
  vespertino: vespertino as ContextoEstudante,
} as const;

export const PROPOSTA = {
  higiene_sono: higiene_sono as PropostaGrade,
  reducao_danos: reducao_danos as PropostaGrade,
  refeicao: refeicao as PropostaGrade,
  sobrecarga_fadiga: sobrecarga_fadiga as PropostaGrade,
  sobrecarga_noturna: sobrecarga_noturna as PropostaGrade,
  valida: valida as PropostaGrade,
  violacoes: violacoes as PropostaGrade,
} as const;

export const RESULTADO = {
  aprovado: aprovado as ResultadoValidacao,
  reprovado: reprovado as ResultadoValidacao,
  sobrecarga: sobrecarga as ResultadoValidacao,
} as const;

export const COMMUNICATION = {
  checkins,
  evidencias,
  grade,
} as const;
