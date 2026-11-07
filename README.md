# Chronos Hub

O Chronos Hub reúne cadastro de clientes, gestão de equipe, estoque, loja e agenda em uma interface React. Esta distribuição local seleciona os módulos do sistema comercial que podem ser exercitados com uma empresa fictícia. O [inventário de revisão](MATERIAIS-REVISADOS.md) descreve a seleção e as limitações.

### Executar no Windows

Use Python 3.11 e Node.js 22.12 ou superior compatível com Vite 7. A partir da raiz, crie o ambiente, instale as dependências e inicialize a empresa fictícia:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_preview.py --demo
npm.cmd --prefix Chronos_UI ci --ignore-scripts --no-audit
```

No primeiro terminal, inicie as APIs. O comando usa somente portas locais e para se alguma delas estiver ocupada. Ctrl+C encerra os processos iniciados por ele.

```powershell
.\.venv\Scripts\python.exe run_local.py
```

Em outro terminal na mesma pasta:

```powershell
npm.cmd --prefix Chronos_UI run dev
```

Abra **http://127.0.0.1:18800/ChronosCore/login**, procure por `demo` e selecione a empresa. Entre com `demo@example.invalid` e a senha provisória gerada no campo `PREVIEW_DEMO_PASSWORD` do `.env` local. Escolha a nova senha no primeiro acesso. No menu, use **Clientes** para cadastrar um contato fictício ou **Estoque** para adicionar um item. Loja e Agenda têm telas de administração e rotas públicas locais.

O Core emite o token de sessão usado pelos módulos. A API administrativa possui autenticação independente, com documentação em http://127.0.0.1:18805/docs. O usuário de exemplo é `admin-local` e sua senha inicial está em `PREVIEW_INITIAL_ADMIN_PASSWORD`. Nunca envie esses valores ao Git.

### Dados e configuração

`init_preview.py` gera quatro valores exclusivos em `.env`. Uma nova execução conserva a configuração existente. Sem `--demo`, o script apenas prepara os segredos. As APIs inicializam os bancos e arquivos em `.local/`. Core, Nexus e ADM usam SQLite. Estoque, Loja, Agenda e Media usam persistência local por arquivo nesta distribuição. O schema PostgreSQL e as migrations são referências técnicas. Os recursos que exigem PostgreSQL, como certas operações de variantes ou de importação de catálogo, ficam indisponíveis.

O [piloto integrado de Loja e Estoque](Chronos_loja/README.md) testa importação, reimportação e catálogo público em processos separados.

O [piloto independente do Estoque](Chronos_stock/README.md) inclui os pacotes compartilhados necessários e um teste com duas empresas. A opção `--demo` habilita seis itens novos e inteiramente fictícios no primeiro estoque local.

As versões instaláveis dos pilotos e as instruções de execução estão no [guia de pacotes](PACOTES.md).

O [guia de atualização](ATUALIZACAO.md) descreve como conservar a configuração, o estoque e o catálogo já existente.

### Verificar

```powershell
.\.venv\Scripts\python.exe verify_preview.py
npm.cmd --prefix Chronos_UI run build
git ls-files
python audit_index.py
```

Os testes usam outra pasta temporária, outra configuração e dados inventados. O auditor lê o índice Git; os arquivos em `.env`, `.local/`, `node_modules/` e `dist/` não fazem parte da distribuição. Consulte também [arquitetura](ARCHITECTURE.md), [segurança](SECURITY.md) e [contribuição](CONTRIBUTING.md).

Os próximos trabalhos propostos estão no [plano de evolução](ROADMAP.md).

### Autoria e licenças

© 2026 Kronos Hub Dev. O código próprio publicado nesta edição do Chronos Hub, incluindo scripts, schemas e exemplos de código, é distribuído sob a [licença MIT](LICENSE). Os textos de autoria de Kronos Hub Dev nos READMEs, guias e demais documentos Markdown são distribuídos sob [Creative Commons Atribuição 4.0 Internacional](https://creativecommons.org/licenses/by/4.0/deed.pt-br). O texto integral acompanha a distribuição em [LICENSE-DOCS](LICENSE-DOCS).

Ao compartilhar ou adaptar um guia, credite **Kronos Hub Dev**, identifique o guia, inclua o link da licença, indique as alterações e mantenha o link de origem quando fornecido. As marcas e logotipos ficam fora dessa licença de documentação. Materiais e dependências de terceiros conservam seus próprios avisos e licenças.
