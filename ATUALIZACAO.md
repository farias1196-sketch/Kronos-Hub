# Atualizar uma instalação local

O verificador parte da primeira revisão pública `970a8ac`. Ele cria um item fictício, configura um produto publicado na Loja e grava um preço de venda. Em seguida abre uma instalação da revisão atual com uma cópia daqueles dados. Confere saldo, preço, identificador do produto, publicação e integridade do arquivo de configuração.

Com o histórico Git completo e as dependências da raiz instaladas, execute `python verificar_atualizacao.py`. As duas instalações do teste ficam em diretórios temporários. O resultado se aplica ao formato local desta distribuição.

Para atualizar uma instalação própria da prévia:

1. Encerre os serviços da prévia e anote a revisão atual com `git rev-parse HEAD`.
2. Guarde uma cópia privada de `.env` e de toda a pasta `.local/`. Esses arquivos devem permanecer fora do Git.
3. Prepare um checkout novo da revisão escolhida e instale as dependências. Copie nele a configuração e os dados locais da prévia. Para os wheels, inicie ambos os serviços no diretório de dados conforme o [guia de pacotes](PACOTES.md).
4. Confira o login, o saldo de um item conhecido e o preço de um produto publicado. Uma família antiga com origem ambígua pode exigir ajuste no Estoque antes de reimportar.
5. Se a conferência falhar, encerre os serviços atualizados e reabra o checkout anterior com a cópia dos dados anterior à atualização.
