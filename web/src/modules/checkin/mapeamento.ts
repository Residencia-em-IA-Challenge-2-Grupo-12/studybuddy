import type { CheckIn, EscalasCheckIn } from "@/modules/fluxo/types";

/** Conversão interina entre as quatro escalas da issue e os três campos do contrato `CheckIn`.
 *
 *  | o que a tela pede | para onde vai             |
 *  | ----------------- | ------------------------- |
 *  | humor             | fica no cliente           |
 *  | estresse          | `estresse` (direto)       |
 *  | qualidade do sono | fica no cliente           |
 *  | fadiga            | `energia` = 6 − fadiga    |
 *  | horas de sono     | `horas_sono` (à parte)    |
 *
 *  `horas_sono` é perguntado à parte porque uma escala de 1 a 5 não vira horas, e inventar uma
 *  tabela de conversão seria fabricar dado. Quando o épico 0 decidir incluir humor e fadiga no
 *  contrato, esta função vira identidade e as escalas sobrando somem do estado do fluxo. */
export function paraCheckIn(escalas: EscalasCheckIn, horasSono: number): CheckIn {
  return {
    energia: 6 - escalas.fadiga,
    horas_sono: horasSono,
    estresse: escalas.estresse,
  };
}
