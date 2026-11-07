# Próximos trabalhos propostos

Estimativas para a edição local, sujeitas à priorização do mantenedor. Cada entrega pode ser revista em um commit ou pull request com um teste reproduzível.

| Trabalho proposto | Critério de conclusão | Estimativa |
| --- | --- | --- |
| Persistir as prévias de importação CSV do Estoque | Uma prévia criada em um processo pode ser confirmada por outro. O teste cobre expiração, isolamento entre empresas e duas confirmações concorrentes. | 6–8 h |
| Proteger edições simultâneas na Loja | Dois atendentes alteram produtos diferentes em processos distintos e as duas alterações sobrevivem ao reinício. A edição simultânea do mesmo produto tem resultado documentado e testado. | 6–8 h |
| Exercitar recuperação do armazenamento local | Simular JSON truncado e falha de gravação em dados fictícios, recuperar a partir de uma cópia privada e conferir saldo e histórico. | 4–6 h |
| Revisar acessibilidade do catálogo e do carrinho | Percorrer busca, seleção de variante e alteração da quantidade usando só o teclado. Verificar foco, rótulos e mensagens de erro nas telas cobertas. | 4–6 h |

A soma estimada é de **20 a 28 horas de trabalho futuro**. Os testes de baixa simultânea no Estoque, colisão de famílias na Loja, instalação dos wheels e atualização entre revisões já fazem parte da edição atual.
