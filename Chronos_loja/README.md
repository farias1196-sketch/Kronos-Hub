# Piloto Loja + Estoque

A Loja organiza produtos do Estoque em famílias e permite decidir quais aparecem no catálogo público. Esta seleção contém os serviços reais e os pacotes internos necessários ao fluxo de importação. O conteúdo do piloto sai da lista de arquivos preparados no índice Git. Dados e históricos comerciais ficam fora dessa lista.

### Instalar e testar no Windows

Na raiz da pasta de envio, com Python 3.11 e os arquivos revisados no índice:

```powershell
python Chronos_loja/exportar_piloto.py ../loja-estoque-piloto
cd ../loja-estoque-piloto
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Chronos_loja/requirements.txt
.\.venv\Scripts\python.exe Chronos_loja/verificar_integracao.py
```

O teste usa duas empresas e tokens fictícios em uma pasta temporária. Ele precisa da porta local **18815** livre para o Estoque, porque esse é o destino que a Loja aceita. A Loja usa uma porta de teste atribuída pelo sistema. Se a porta do Estoque estiver ocupada, o teste para antes de acessar o serviço existente.

### Fluxo

1. Criar um item de venda no Estoque de uma empresa.
2. Chamar `POST /shop/products/import-from-stock` com a sessão dessa empresa. A Loja consulta `GET /stock/items` usando seu próprio token de serviço. Uma importação inicial cria a configuração da família; as próximas preservam o preço editado pelo lojista.
3. Publicar explicitamente o produto para que apareça em `GET /public/{slug}/catalog`. Com a exibição de estoque desligada, o catálogo omite quantidade, disponibilidade e parâmetros internos, mas o administrador ainda vê o estoque na área privada.
4. Se o Estoque estiver indisponível, a importação retorna `503`. Um retorno incompatível com a empresa ou com o formato esperado retorna `502`.

Famílias diferentes que geram o mesmo identificador textual recebem IDs separados. Uma reimportação conserva preços, publicação e referências existentes. Quando um catálogo antigo vincula as mesmas configurações a mais de uma família e a origem é ambígua, a importação retorna 409 antes de gravar. Diferencie os nomes no Estoque e revise a associação antes de tentar novamente.

Para executar manualmente, rode `python init_preview.py` na raiz do piloto e inicie, em terminais separados do mesmo ambiente virtual:

```powershell
python -m uvicorn Chronos_stock.stock_api.app.main:app --host 127.0.0.1 --port 18815
python -m uvicorn Chronos_loja.loja_api.app.main:app --host 127.0.0.1 --port 18806
```

O piloto combinado cobre importação e catálogo. Login normal e fluxos que dependem de Core ou Nexus, como registrar o cliente no checkout, exigem a distribuição completa. Operações exclusivas de PostgreSQL continuam desativadas. Veja também [piloto do Estoque](../Chronos_stock/README.md).

### Autoria e licenças

© 2026 Chronos Hub Dev. O código próprio deste piloto usa a [licença MIT](../LICENSE). O texto deste guia usa [CC BY 4.0](../LICENSE-DOCS). Ao redistribuir o guia, credite Chronos Hub Dev e indique as adaptações. [Creative Commons Atribuição 4.0 Internacional](https://creativecommons.org/licenses/by/4.0/deed.pt-br).
