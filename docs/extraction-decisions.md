# Decisões da extração

Escopo aprovado em 09/10/2026: JSON de empresas → crawling intrasite → conteúdo pronto para chunking/classifying. Implementação limitada a este repositório.

Base somente leitura: `antoniofaical/startup-theme-adherence-classifier-jev`, revisão `dbd6c4cc4fb35bb820205b500b2bdf67eb84b34b`, árvore principal `src/`.

## Preservado

- Formato dos registros `evidence.jsonl`.
- Regras de URLs, descoberta intrasite, robots, sitemaps e extração.
- Limites padrão, cache com hashes e recuperação local.
- Deduplicação por nome/URL, primeira ocorrência e ordem da entrada.
- User-Agent `StartupThemeAdherence/2.0`, para conservar a seleção de regras de robots usada pela origem.
- Esquema 2 do estado de coleta. Conteúdo e manifesto atuais são substituídos em novas coletas bem-sucedidas, como na base.

## Separado ou acrescentado

- Removidos perfis, Jev, DeepL, scoring, chunks e RunStore.
- A recuperação verifica texto diretamente, sem importar o particionador.
- Nova CLI do coletor e pacote instalável com dependências próprias.
- `batch.json` versão 1 contém identidade, caminhos, hashes, cobertura e erros de todas as empresas únicas selecionadas. Evita exigir que o consumidor leia o JSON de entrada do coletor.
- A tentativa com zero páginas expõe seu diretório de diagnóstico. Em falhas, o índice não referencia conteúdo antigo.
- `crawl_config` no manifesto e verificação dos valores disponíveis na recuperação: impedem atribuir uma configuração nova a uma coleta feita com limites diferentes.
- Nomes de saída reservados ou em conflito com `batch.json` são rejeitados para permitir o mesmo comportamento no Windows e no Linux.
- Leitura de JSON com BOM UTF-8 e logs de progresso em stderr.
- Links são explorados antes de descartar conteúdo duplicado: duas páginas com texto igual podem ter iframes diferentes. O teste de regressão demonstra que ambos os destinos continuam sendo coletados.
- Estrutura mínima criada na principal para permitir um PR de implementação no repositório inicialmente vazio.

## Limites

A validação automática usa HTTP simulado e servidor local; não comprova cobertura de sites reais. Sites dependentes de JavaScript, documentos escaneados e autenticação seguem fora do escopo da primeira entrega. Os testes do classifier e a integração com Jev pertencem ao repositório seguinte.
