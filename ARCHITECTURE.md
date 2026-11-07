# Arquitetura local

A interface Vite/React roda em 127.0.0.1:18800 e acessa o proxy de mesma origem em `/api/<módulo>`. O proxy aceita uma lista fixa de serviços locais. A interface usa as telas do CRM com uma navegação adaptada aos módulos disponíveis.

| Serviço | Porta | Papel na distribuição |
| --- | --- | --- |
| Core | 18802 | Empresa, equipe, primeiro acesso, sessão e permissões |
| Nexus | 18803 | Clientes, contatos, tags e registro público |
| ADM | 18805 | Login e administração próprios |
| Loja | 18806 | Catálogo, carrinhos, orçamentos e pedidos |
| Agenda | 18807 | Serviços, horários e agendamento público |
| Media | 18809 | Armazenamento local de imagens PNG e JPEG |
| Estoque | 18815 | Itens, categorias e movimentações |

O funcionário autentica-se no Core. Cada API verifica o JWT e o escopo da empresa antes de acessar os recursos protegidos. O ADM usa sua própria chave. A Loja consulta o estoque e o Nexus usando credenciais de serviço; a Agenda consulta Loja e Estoque. Esses pedidos ficam restritos a serviços da cópia com portas fixas, sem redirecionamentos HTTP. O ADM não sonda serviços da infraestrutura comercial.

SQLite e arquivos JSON ficam em `.local/`. O Media valida o conteúdo das imagens, recria a miniatura e restringe leitura e exclusão à pasta da empresa. O acesso público a imagens selecionadas depende de assinatura com validade limitada. A autenticação e o armazenamento compartilhados estão em `chronos_auth/` e `chronos_storage/`. Os SQLs e os dois schemas Prisma documentam modelos reais; não são executados pelos comandos de inicialização.
