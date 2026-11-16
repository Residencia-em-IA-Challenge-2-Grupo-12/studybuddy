"""Pipeline multiagente: Agente de Triagem + Agente Planejador, coordenados pelo orquestrador.

- triagem.py      -> diagnostica o estudante (problema, objetivo, restrições), DECIDE se a resposta é um
                     plano ou uma explicação e escreve consultas para a base
- planejador.py   -> verifica o escopo (porteiro), reúne evidências com a pergunta + as consultas da
                     Triagem e escreve a resposta no formato decidido, dentro das restrições, citando a fonte
- orquestrador.py -> chama os dois em ordem e aplica o atalho do porteiro
"""
