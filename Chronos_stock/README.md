# Piloto independente do Estoque

Esta edição da API de estoque usa os fontes locais revisados, incluindo `chronos_auth` e os auxiliares de `chronos_storage`. Os dados de teste são criados em disco local. O commit comercial e seus catálogos não integram este pacote.

### Preparar uma instalação limpa

Na raiz da pasta de envio, após revisar o índice, execute o exportador com o caminho de uma **nova pasta irmã**. Ele seleciona os arquivos do índice Git por nome; não copia o histórico, o ambiente virtual, o banco ou o arquivo privado de configuração.

```powershell
python Chronos_stock/exportar_piloto.py ../estoque-piloto
cd ../estoque-piloto
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r Chronos_stock/requirements.txt
.\.venv\Scripts\python.exe init_preview.py
.\.venv\Scripts\python.exe Chronos_stock/verificar_piloto.py
```

A verificação usa instalações temporárias, empresas e tokens SSO fictícios e portas de loopback escolhidas pelo sistema. Exercita a API por HTTP, encerra o processo e abre outro para verificar o estado persistido. O servidor de teste não usa os segredos fornecidos ao piloto.

### Usar o serviço

O estoque começa vazio. Se quiser começar com **três produtos de venda e três materiais internos fictícios**, antes da primeira inicialização execute `.\.venv\Scripts\python.exe -m Chronos_stock.demo_items`. Isso habilita exemplos exclusivamente para a empresa `demo` em um estoque novo; dados já existentes e itens removidos não são repostos. No Hub completo, a opção `init_preview.py --demo` também habilita esses itens.

Na raiz do piloto, inicie a API com:

```powershell
.\.venv\Scripts\python.exe -m uvicorn Chronos_stock.stock_api.app.main:app --host 127.0.0.1 --port 18815
```

`GET /health` é público. A autenticação normal usa um token de funcionário emitido pelo Core do mesmo ambiente local. O piloto independente contém a validação do token; não inclui a tela de login ou a API do Core. Para login de ponta a ponta, execute a distribuição completa. A geração de tokens de teste fica restrita à verificação temporária.

Cada empresa tem sua própria pasta de snapshot, identificada pelo hash do seu identificador exato, inclusive no Windows. O identificador original fica no JSON. Snapshots gerados em versões anteriores podem permanecer no layout antigo; a API recria o arquivo no novo layout na próxima operação, sem ler nem apagar o antigo. O estoque principal continua no mesmo `.local/stock/stock_data.json`.

Os recursos que exigem PostgreSQL, como a importação conjunta com a Loja, não são habilitados aqui. Este piloto verifica o funcionamento técnico do módulo e não substitui o histórico autêntico para a inscrição.

### Autoria e licenças

© 2026 Kronos Hub Dev. O código próprio deste piloto usa a [licença MIT](../LICENSE). O texto deste guia usa [CC BY 4.0](../LICENSE-DOCS). Ao redistribuir o guia, credite Kronos Hub Dev e indique as adaptações. [Creative Commons Atribuição 4.0 Internacional](https://creativecommons.org/licenses/by/4.0/deed.pt-br).
