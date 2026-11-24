"""Pipeline multiagente e camada de validação/guardrails.

- triagem.py      -> diagnostica o estudante (problema, objetivo, restrições), DECIDE se a resposta é um
                     plano ou uma explicação e escreve consultas para a base
- planejador.py   -> verifica o escopo (porteiro), reúne evidências com a pergunta + as consultas da
                     Triagem e escreve a resposta no formato decidido, dentro das restrições, citando a fonte
- orquestrador.py -> chama os dois em ordem e aplica o atalho do porteiro
- contratos.py    -> contratos JSON (Pydantic) trocados entre os agentes e o provedor de agenda
- guardrails.py   -> contrato e parser fail-closed dos guardrails via LLM (barreiras 4.4 a 4.7)
- validation.py   -> validação determinística (sem LLM) da grade: CONFLITO_AGENDA e INTEGRIDADE_CIRCADIANA
"""
