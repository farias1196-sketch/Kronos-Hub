# Inventário da revisão

| Material do Hub | Decisão e motivo |
| --- | --- |
| Core, Nexus, ADM e pacotes compartilhados | Incluídos os serviços e os fontes necessários ao uso local. O ADM usa chave própria e provisionamento local. Reset anônimo, importação do legado, espelhamento e sondagens comerciais ficam de fora. |
| Chronos_UI | Incluídas as telas de login, Core, clientes, estoque, loja e agenda com suas dependências de código. Rotas locais, dados de exemplo e navegação foram adaptados. Builds antigos, sites, imagens de marcas, testes de deployment e componentes de apresentação ligados a serviços excluídos ficam de fora. |
| Estoque, Loja, Agenda | Incluídas as APIs reais, os auxiliares de armazenamento e de geração de documentos. Persistência local, empresa de demonstração e consultas entre serviços limitadas à instalação local. O envio inclui código que gera documentos e não inclui documentos produzidos por usuários. |
| Chronos Media | Incluída a API de imagens em disco, com limite de 8 MiB, validação de formato, diretórios por empresa e testes. O recorte suporta PNG e JPEG. Material OAuth, cache existente, uploads comerciais e arquivos de outros tipos ficam de fora. |
| Banco e Chronos Prisma | Incluídos schema SQL, nove migrations e schema Prisma revisados. Sem relatórios, snapshots, registros ou scripts de importação operacional. |
| Zap e fila | Incluído apenas o modelo Prisma da fila. Pareamento, conversas, chaves, outbox, ponte Baileys e conexão WhatsApp ficam de fora. A distribuição da ponte requer análise própria das licenças das dependências. |
| Flow | A tela original acopla o fluxo de atendimento à conversa e ao envio de mensagens do Zap. Esse fluxo não foi habilitado nesta seleção. |
| Synchronization e Evolution Test | Gerenciam instâncias, webhooks e conexão a provedores. Código de provisionamento, ambiente de teste integrado e exportações não entram na distribuição local. |
| Pay e Log | OAuth, webhooks, tokens de provedores, cobranças e contratação de frete têm efeitos externos. Os módulos comerciais e suas configurações não foram incluídos. |
| Promoções | O editor e a geração de encartes usam modelos, imagens e referências comerciais. Os arquivos de arte e o editor dependem de revisão de titularidade antes de distribuição. |
| Hera AI | Conecta modelos, transcrição e histórico de conversas. A inclusão exige decisão sobre os modelos, os dados e a elegibilidade do escopo de IA. |
| ADM desktop e portal separado de clientes | O desktop contém controle de serviços e infraestrutura. O portal separado trabalha com contas, contratos e documentos. Ambos ficam fora deste lote. |
| Documentação interna, ferramentas e artefatos | Foram excluídos manuais comerciais, recuperação de acesso, deploy, backups, logs, dados operacionais, PDFs, planilhas, mídia, diretórios temporários e ambientes instalados. |

Esta é uma revisão da distribuição selecionada. Não comprova direitos sobre ativos excluídos, segurança de todos os módulos em produção nem elegibilidade do CRM no programa. O histórico Git comercial não foi copiado ou reescrito.
