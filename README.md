# Institutional Site Snowballer

Recebe um JSON com empresas e URLs, percorre links dentro de cada site e entrega o conteúdo das páginas para chunking e classificação posteriores.

O pacote funciona sozinho. Não carrega perfis, não cria chunks e não chama Jev ou DeepL.

## Instalação

Python 3.11 ou superior, em ambiente virtual:

~~~text
python -m pip install .
~~~

Para extrair PDFs textuais, instale `.[pdf]`. Para desenvolvimento, instale `.[dev]`.

## Uso

Crie `sites.json`:

~~~json
[
  {"name": "Empresa A", "url": "https://empresa-a.example/"},
  {"name": "Empresa B", "url": "https://empresa-b.example/"}
]
~~~

Substitua as URLs de exemplo pelas URLs das empresas e execute:

~~~text
institutional-site-snowballer --sites-file sites.json --output-dir coleta/
~~~

Também funciona com `python -m institutional_site_snowballer`.

A saída é:

~~~text
coleta/
  batch.json
  Empresa-A/
    evidence.jsonl
    manifest.json
    crawl_state.json
  Empresa-B/
    evidence.jsonl
    manifest.json
    crawl_state.json
~~~

Cada linha de `evidence.jsonl` contém `url`, `content_type`, `language_hint` e `text`. O texto é extraído do HTML: título, descrição e conteúdo visível, com scripts e estilos removidos. Não é HTML bruto nem HTML renderizado por navegador. O conteúdo textual coletado é preservado inteiro; não há truncamento ou amostragem para classificação.

`batch.json` identifica cada empresa e seus arquivos com caminhos relativos. Uma falha permanece no índice, com erro e sem apontar para uma coleta antiga. O futuro classifier pode receber somente esse lote, sem precisar do JSON de sites original. Consulte o [contrato de conteúdo](docs/content-contract.md).

## Controles

~~~text
institutional-site-snowballer --sites-file sites.json --output-dir coleta/ --workers 4
institutional-site-snowballer --sites-file sites.json --output-dir coleta/ --site "Empresa A"
institutional-site-snowballer --sites-file sites.json --output-dir coleta/ --force-crawl
institutional-site-snowballer --sites-file sites.json --output-dir coleta/ --recover-existing-crawls
~~~

- Coletas recentes são reutilizadas quando nome, URL, configuração e hashes coincidem. O prazo padrão é 24 horas (`--crawl-max-age-hours`).
- `--force-crawl` faz uma nova tentativa; se falhar, os arquivos antigos permanecem, mas o novo índice registra a falha e não os oferece como resultado da tentativa.
- `--recover-existing-crawls` verifica artefatos existentes e reconstrói o estado sem acessar a rede. Conserva o horário da coleta e verifica configurações registradas; não pode ser combinado com `--force-crawl`.
- `--site` pode ser repetido; `--sites` aceita vários nomes. Os nomes de aliases duplicados selecionam a primeira ocorrência.
- `--no-progress` oculta o progresso; `-v` amplia detalhes e `--traceback` mostra falhas inesperadas.

Limites padrão, preservados da origem:

| Opção | Padrão |
|---|---:|
| `--max-pages-per-site` | 400 páginas salvas |
| `--max-requests-per-site` | 500 tentativas de páginas |
| `--max-queue-size` | 2.000 URLs em fila |
| `--max-crawl-seconds` | 900 segundos |
| `--max-sitemaps-per-site` | 50 sitemaps |
| `--request-timeout` | 20 segundos por requisição |

Zero desativa cada limite de coleta; o timeout precisa ser positivo. As consultas a robots e sitemaps não entram no contador de tentativas de páginas. O limite de tempo é conferido entre requisições, portanto uma requisição em curso pode ultrapassá-lo até seu timeout.

## Escopo e resultados

O padrão segue links no mesmo host, incluindo a equivalência com `www`, e respeita robots. Subdomínios adicionais e parâmetros de consulta ficam fora do escopo padrão. Redirecionamentos externos não são salvos como evidência. Não há descoberta entre empresas ou verificação de autenticidade institucional.

Nomes ou URLs equivalentes são deduplicados antes da coleta; prevalece a primeira ocorrência. Colisões de diretório e nomes reservados são rejeitados antes da execução. Conteúdo textual repetido é salvo uma vez, mas seus links continuam sendo explorados.

Limites ou erros de páginas marcam a evidência como parcial. `completed` no índice significa que os artefatos foram produzidos; não garante cobertura integral. Robots e erros de sitemaps seguem a interpretação de cobertura da origem. Páginas sem texto podem ser registradas; `has_text` informa se o conjunto tem texto utilizável.

Códigos de saída: **0** para todas as empresas com artefatos produzidos (inclusive coletas parciais); **1** quando alguma empresa falha; **2** para entrada/opções inválidas ou erro geral de saída. Uma falha de empresa não interrompe as outras. Use um diretório de saída por lote e uma execução ativa por diretório. Novas execuções substituem o índice e os arquivos atuais de coletas bem-sucedidas, como na origem.

## Verificação

~~~text
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python -m pytest -q
python -m build --wheel
~~~

O CI verifica Python 3.11 e 3.12 no Linux e 3.12 no Windows, além da instalação do wheel em ambiente independente. Os testes unitários bloqueiam conexões de rede; o teste do pacote instalado usa apenas um servidor HTTP local simulado.

## Origem

Extraído da árvore principal `src/` de [startup-theme-adherence-classifier-jev](https://github.com/antoniofaical/startup-theme-adherence-classifier-jev), revisão [dbd6c4cc4fb35bb820205b500b2bdf67eb84b34b](https://github.com/antoniofaical/startup-theme-adherence-classifier-jev/commit/dbd6c4cc4fb35bb820205b500b2bdf67eb84b34b). O repositório de origem é somente leitura. Consulte [as decisões de extração](docs/extraction-decisions.md).
