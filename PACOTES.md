# Instalar os pilotos por versão

Estoque e Loja podem ser instalados como pacotes Python. Ambos dependem da versão exata `0.1.0` de `chronos-hub-shared`, que fornece autenticação, configuração e armazenamento. A Loja consulta a API do Estoque por HTTP. Os três pacotes são construídos localmente a partir do índice Git da edição pública. Cada wheel inclui os dois textos de licença.

Com Python 3.11, execute na raiz do checkout revisado. Escolha diretórios novos.

```powershell
python empacotar_pilotos.py ..\chronos-wheels
python -m venv ..\chronos-pilotos-venv
$python = (Resolve-Path ..\chronos-pilotos-venv\Scripts\python.exe).Path
$pacotes = (Get-ChildItem ..\chronos-wheels -Filter '*.whl').FullName
& $python -m pip install $pacotes
& $python -m pip check
& $python -I verificar_pacotes.py
```

Para instalar somente o Estoque, passe ao pip os arquivos locais `chronos_hub_shared` e `chronos_hub_stock`. Para usar a integração, instale os três. A construção e a instalação baixam as dependências externas declaradas pelo projeto. O teste roda os serviços instalados em diretórios temporários e usa a porta de loopback 18815 para a integração.

Para executar os pilotos, escolha um diretório de trabalho novo fora do checkout. Os dois serviços devem iniciar nesse mesmo diretório para ler a mesma configuração. No primeiro terminal:

```powershell
New-Item -ItemType Directory ..\chronos-pilotos-dados | Out-Null
Set-Location ..\chronos-pilotos-dados
& $python -I -m init_preview
& $python -I -m Chronos_stock.demo_items
& $python -I -m uvicorn Chronos_stock.stock_api.app.main:app --host 127.0.0.1 --port 18815
```

No segundo terminal, entre no mesmo diretório e use o executável do mesmo ambiente virtual para iniciar `-I -m uvicorn Chronos_loja.loja_api.app.main:app --host 127.0.0.1 --port 18806`. O estoque de exemplo é opcional. O login do Core e o painel ADM fazem parte do Hub completo. A configuração e os dados dos pilotos ficam em `.env` e `.local/` dentro do diretório de trabalho.
