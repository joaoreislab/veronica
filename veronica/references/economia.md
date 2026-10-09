# Economia com preservação

O núcleo reduz repetição e processamento redundante. Não restringe o raciocínio, a escolha de modelo, a extensão das respostas nem a quantidade de informação que pode ser consultada. Informações completas ficam no projeto; uma janela ativa finita exige consultar fontes conforme o trabalho, sem garantia de que todos os detalhes estarão simultaneamente no prompt.

## Artefatos exatos

`scripts/preserve.py` usa apenas a biblioteca padrão Python. Sempre informe `--workspace PROJETO`. Nos exemplos, `python`, `SKILL` e `PROJETO` representam os caminhos reais do host; não execute os marcadores literalmente.

```text
python SKILL/scripts/preserve.py --workspace PROJETO capture --file outputs/log.txt
python SKILL/scripts/preserve.py --workspace PROJETO read --artifact HASH
python SKILL/scripts/preserve.py --workspace PROJETO read --artifact HASH --start 30 --end 80
python SKILL/scripts/preserve.py --workspace PROJETO search --artifact HASH --query "erro específico"
python SKILL/scripts/preserve.py --workspace PROJETO search --artifact HASH --query "erro" --offset 0 --limit 20
python SKILL/scripts/preserve.py --workspace PROJETO restore --artifact HASH --output outputs/log-recuperado.txt
python SKILL/scripts/preserve.py --workspace PROJETO compact --artifact HASH
python SKILL/scripts/preserve.py --workspace PROJETO compact --artifact HASH --render
```

Capture copia os bytes de um arquivo já produzido, incluindo dados binários. Não executa o comando de origem. Metadados opcionais entram por `--metadata ARQUIVO_JSON`; declare comando, exit code, origem e escopo quando conhecidos. A captura de um arquivo sendo escrito registra os bytes lidos, não um snapshot transacional do processo produtor: espere a escrita terminar quando consistência exigir.

O identificador é SHA256. Blobs iguais são compartilhados, mas cada captura mantém uma origem separada. O catálogo e os originais ficam em `work/veronica/artifacts/`, separados do ledger. Recuperação exige um destino novo fora do estado; não sobrescreve arquivos. Nenhuma expiração/limpeza automática remove dados. Para transferência a outra máquina, copiar somente o checkpoint do ledger não copia estes artefatos; inclua a pasta de artefatos e os arquivos do produto pertinentes.

Leitura e busca verificam a identidade do blob. Texto usa UTF-8 com quebras de linha preservadas; arquivo não UTF-8 continua recuperável como bytes e não é convertido silenciosamente. A leitura sem faixa retorna tudo. Busca é literal e sensível a maiúsculas; não remove stopwords, não interpreta regex e não decide relevância. Sem `--limit`, retorna todas as ocorrências. Páginas informam total, continuidade e disponibilidade do original. Uma busca sem resultado pede outra consulta/leitura, não conclusão semântica.

## Compacidade reversível

`compact` retorna um frame JSON `raw` ou `lines-v1`. Ambos trazem tamanho original e SHA256. `lines-v1` contém um dicionário de linhas exatas e sequências `[índice, repetições]`, incluindo suas terminações. O decoder `expand(frame)` reconstrói o texto e confere tamanho/hash. Ordem, repetições, espaços e Unicode são preservados. O encoder verifica a reconstrução e só escolhe o frame compacto quando ele é menor que o texto original em bytes UTF-8. Sem `--render`, a saída sempre tem envelope JSON para máquinas, cujo custo precisa ser considerado. Com `--render`, a saída é o frame compacto quando menor, ou o texto original exato sem envelope extra. O consumidor deve conhecer esse modo explícito. A contagem é de bytes, não tokens de um modelo.

Use esse formato quando repetição extensa justificar a representação e o consumidor entendê-la. Para editar código ou examinar um detalhe literal, prefira leitura do trecho original. Equivalência dos bytes não prova que um modelo interpreta qualquer formato com a mesma qualidade; não aplique compactação universal ao host. Protocolos de ferramentas, pipelines e âncoras de edição permanecem em seu formato esperado.

## Estado e verificações

```text
python SKILL/scripts/veronica.py --workspace PROJETO context
python SKILL/scripts/veronica.py --workspace PROJETO context --task ID
python SKILL/scripts/veronica.py --workspace PROJETO context --task ID --index-limit 20 --index-offset 0
python SKILL/scripts/veronica.py --workspace PROJETO context --compact
python SKILL/scripts/veronica.py --workspace PROJETO resume --full
```

`context` inclui os mesmos campos de `status`, sem tokens de posse. A seleção explícita de tarefa inclui dependências, todas as notas/efeitos globais e um índice das demais tarefas; informa que é uma visão parcial e como abrir o projeto completo. Não elimina critérios, falhas nem evidências das tarefas selecionadas. A opção compacta é reversível.

Em 1.1.2, `--index-limit` e `--index-offset` paginam somente o índice das tarefas não selecionadas. `task_index_page` informa total, continuidade e completude. A tarefa, suas dependências e todas as notas/efeitos globais permanecem completos. Sem essas opções, a consulta mantém seu comportamento anterior. O índice paginado reduz o retorno; a verificação ainda examina o estado do projeto e não promete redução de processamento local.

Hashes de arquivos de evidência são reaproveitados apenas dentro de uma chamada de `status`, com metadados de arquivo no identificador local. A próxima chamada começa sem cache, e falha de hash nunca vira evidência aceita. Esse reuso não certifica alterações concorrentes ou maliciosas com metadados falsificados; como antes, estabilize os insumos durante uma verificação.

As projeções JSON, Markdown e painel de uma publicação compartilham o mesmo estado verificado, evitando verificar tudo três vezes e mantendo uma fotografia consistente. Uma nova publicação verifica novamente.

## Uso observado

`usage-record --input ARQUIVO_JSON` registra um evento; `usage` devolve registros e grupos por origem/modelo/tarefa. ID repetido com os mesmos dados não duplica contagem; dados divergentes exigem reconciliação. Não importe contadores cumulativos como se cada linha fosse uma chamada: derive deltas comprovados ou mantenha-os como snapshots separados fora da soma.

```json
{"id":"request-123","source_kind":"provider","source":"response usage observado","model":"modelo-observado","task":"tarefa-a","input_tokens":1000,"cached_input_tokens":600,"output_tokens":100,"reasoning_output_tokens":40}
```

Tipos de origem: `provider`, `local_log`, `estimate`. Neste contrato cache read/write são subconjuntos disjuntos do input e reasoning é subconjunto de output. Adapte a semântica do provedor antes de registrar. Campo ausente fica desconhecido; estimativas não são mescladas com uso observado. Total é input + output, sem somar cache/reasoning outra vez. Não há preço embutido, leitura automática da conta, cobrança de assinatura, quota ou mudança de modelo.

Identidades `model` e `task` aceitam texto ou ausência. Inserção idempotente usa exclusão SQLite também com escritores concorrentes. Dados legados inválidos permanecem no catálogo e são relatados em `invalid_records`; `complete: false` impede interpretar os grupos válidos como contagem integral. Recibos de captura e recuperação estão em [recuperacao.md](recuperacao.md).

## Escolha de capacidades

Sempre considere a alternativa capaz de eliminar uma ineficiência real: agente, skill, conector, plugin, CLI, biblioteca ou implementação direta. A decisão inclui instalação/indexação, schema/contexto, chamadas extras, latência, recursos locais, qualidade e repetição. Capacidade atual conhecida pode ser reutilizada; problema novo justifica descoberta dirigida. Estimativa de vantagem é hipótese, não ganho medido.

Escolha a solução suficiente para a tarefa, preserve liberdade de ampliar e rever a escolha, e registre a razão quando a decisão for material. Ferramenta disponível não é pré-requisito obrigatório. Modelos de compressão, roteadores de modelos e agentes adicionais não são acionados automaticamente para economizar.

## Comparação

Teste recurso isolado, pares relevantes, grupos e conjunto. Inclua conteúdo pouco repetitivo, restrição antiga decisiva, erro raro, Unicode/CRLF, arquivo alterado, recuperação integral e chamada repetida. Verifique resposta esperada e originais antes de comparar tamanhos ou tempo. Ganho local de bytes/IO não demonstra custo total de API, qualidade geral do modelo nem sucesso de todo projeto.
