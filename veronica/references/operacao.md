# Operação do núcleo

Python 3.10+ com biblioteca padrão. O banco usa transações SQLite `BEGIN IMMEDIATE` e `synchronous=FULL`. Mutações e eventos entram na mesma transação. JSON, Markdown e HTML são projeções regeneráveis. Use disco local com bloqueio SQLite confiável; sincronização de arquivos em nuvem ou compartilhamento de rede não é coordenação distribuída suportada.

## CLI

Descubra o executável Python do host. Nos exemplos abaixo, `python` representa esse executável, `SKILL` a pasta real da skill e `PROJETO` o workspace absoluto. Não copie esses marcadores como caminhos reais.

```text
python SKILL/scripts/veronica.py --workspace PROJETO init --input work/inicio.json
python SKILL/scripts/veronica.py --workspace PROJETO apply --input work/comando.json
python SKILL/scripts/veronica.py --workspace PROJETO status
python SKILL/scripts/veronica.py --workspace PROJETO resume
python SKILL/scripts/veronica.py --workspace PROJETO checkpoint --reason "Marco conferido, próxima etapa definida"
python SKILL/scripts/veronica.py --workspace PROJETO dashboard
python SKILL/scripts/veronica.py --workspace PROJETO doctor
```

Em PowerShell, use `& 'caminho/python.exe' 'caminho/veronica.py' ...`. Grave JSON com ferramenta de arquivos ou serialização nativa, sem construir comandos por interpolação de conteúdo. `init` nunca sobrescreve um projeto existente. `apply` recebe uma operação. Saída JSON, sucesso 0 e erro de operação 2. `resume --max-chars 9000` limita o resumo, preservando o banco.

### Inicialização e tarefa

```json
{"goal":"Pesquisar opções e entregar um relatório conferido","limits":{"max_active":2,"max_attempts":3,"repeat_failure":2}}
```

Os limites são configuráveis. Na versão 1.1, projetos novos usam `max_attempts: 0` e `repeat_failure: 0`: sem teto automático de tentativas nem bloqueio automático por repetição. O exemplo acima demonstra limites explícitos opcionais. Projetos existentes preservam a configuração anterior; alterar exige `limits` com `reason`. Limites não autorizam encerrar o pedido antes de resolver alternativas viáveis nem aumentam limites do host. O padrão de duas reservas simultâneas protege recursos/áreas de escrita.

```json
{
  "op":"task.add","id":"fontes","title":"Conferir fontes primárias",
  "depends":[],"paths":["work/fontes"],"strategy":"consulta direta",
  "next":"Abrir as fontes e anotar cobertura",
  "criteria":[{"id":"proveniencia","title":"Conclusões têm fontes abertas e datadas","kind":"source"}]
}
```

Dependências precisam existir. Como tarefas novas só apontam para tarefas existentes e dependências são imutáveis na versão 1, a construção é acíclica. Para corrigir o plano, adicione tarefa nova e documente o motivo. Não edite o banco por fora para contornar invariantes. Cada critério tem ID único dentro da tarefa.

`paths` lista arquivos ou diretórios onde a tarefa poderá escrever. `[]` serve para leitura. Uma reserva cobre descendentes e impede outra tarefa cooperante de reservar pai/filho sobreposto. Os caminhos precisam permanecer no workspace após resolução, inclusive links simbólicos. O diretório de estado Veronica não pode ser reservado nem anexado como evidência. A reserva não bloqueia o sistema de arquivos.

### Reserva e continuidade

```json
{"op":"task.claim","id":"fontes","owner":"executor principal","seconds":1800}
```

O recibo contém `token`. Envie-o nos comandos que modificam a tentativa: `task.renew`, `task.next`, `evidence.add`, `task.complete`, `task.fail` e `task.release`. Token errado ou vencido é recusado. A retomada de reserva expirada cria nova tentativa e novo token. O token é controle cooperativo, não credencial de segurança. O banco é privado ao workspace, sem autenticação multiusuário.

```json
{"op":"task.next","id":"fontes","token":"TOKEN_DO_RECIBO","next":"Conferir a fonte que contradiz o dado de prazo"}
```

`task.renew` aceita `seconds` entre 1 e 86400. Renove antes do vencimento, sem iniciar outra tentativa. `task.release` exige `next` e aceita `state` igual a `todo`, `blocked` ou `waiting`. Libere tarefas quando a ação independente terminou ou for necessária ação humana. `task.unblock` exige `reason`, após resolver a causa; não confunda tempo decorrido com autorização.

### Evidência e conclusão

Tipos: `file` para inspeção de conteúdo, `runtime` para execução/testes, `source` para informação conferida em fonte e `human` para observação ou aceitação humana realmente recebida. Tipos devem corresponder ao critério. Registrar uma observação humana não cria aprovação.

```json
{
  "op":"evidence.add","id":"fontes","token":"TOKEN_DO_RECIBO",
  "criterion":"proveniencia","kind":"source",
  "url":"https://exemplo.org/fonte-primaria","ttl_hours":24,
  "files":["work/fontes/trecho-conferido.md"],
  "method":"Página original aberta e comparada com as conclusões",
  "result":"Autoria, data e condições conferidas nos trechos citados",
  "limitations":"Cobertura restrita às perguntas desta tarefa"
}
```

O exemplo de URL é ilustrativo. Evidências reais precisam vir do trabalho realizado. `source` exige URL e validade em horas. `human` exige validade. `file` e `runtime` exigem ao menos um arquivo. Anexe logs e os insumos relevantes para invalidar a evidência quando mudarem. Para execução, incluir somente o log deixa mudanças no código fora da cobertura de hashes.

O helper não abre URLs nem executa o método registrado. O agente relata uma verificação que já fez. Hashes demonstram identidade do arquivo anexado, não correção do conteúdo. Campos `method`, `result` e `limitations` precisam descrever o observado. Não use `evidence.add` para falhas ou testes não feitos; registre falha ou pendência.

```json
{"op":"task.complete","id":"fontes","token":"TOKEN_DO_RECIBO"}
```

Todos os critérios precisam de evidência atual na tentativa atual, dependências precisam de aceitação atual e os efeitos externos precisam estar resolvidos. A aceitação das dependências fica vinculada à tentativa. Se uma dependência for refeita e receber nova aceitação, os dependentes precisam revalidar. Arquivo alterado, removido ou prazo vencido produz `stale`, sem apagar o histórico.

### Falhas e estratégia

```json
{"op":"task.fail","id":"fontes","token":"TOKEN_DO_RECIBO","signature":"fonte-inacessivel","reason":"A página exige acesso que não está disponível","next":"Procurar fonte primária alternativa para o mesmo dado"}
```

Ao repetir a mesma assinatura até `repeat_failure`, o bloqueio exige uma estratégia diferente com motivo:

```json
{"op":"task.strategy","id":"fontes","strategy":"documentação oficial alternativa","reason":"As duas tentativas anteriores falharam na mesma restrição de acesso"}
```

Essa operação mantém a contagem total. `limits` pode ajustar um limite quando houver justificativa dentro do escopo autorizado:

```json
{"op":"limits","limits":{"max_attempts":4},"reason":"Há uma abordagem nova e verificável após o diagnóstico"}
```

### Notas e efeitos externos

`note` aceita `kind` igual a `decision`, `finding`, `handoff` ou `lesson` e `text`. Notas pertencem ao projeto. Não são memória pessoal global.

Para ação externa autorizada, registre `effect.prepare` com `id`, `token`, `key` único e `description`. Logo antes da chamada real, use `effect.start` com `key` e token. Depois observe o destino e use `effect.resolve` com `key`, `state` e `observation`.

Estados de resolução: `confirmed` quando confirmado no destino, `not_applied` quando há evidência de que não ocorreu, `unknown` quando continua incerto. O helper nunca executa essa chamada. `started` ou `unknown` impede retomada automática e repetição sob a mesma chave. Em interrupção, `effect.resolve` pode registrar reconciliação sem reserva ativa. Preserve evidência da observação. Se confirmado ausente e uma nova tentativa for autorizada, prepare uma chave nova e referencie a reconciliação nas notas.

Esse registro não garante exatamente uma execução. Use chave de idempotência do serviço quando existir e mantenha o resultado observado como critério de entrega.

## Persistência e limites

`work/veronica/veronica.db` é a fonte do estado e dos eventos. `estado.json`, `RETOMAR.md` e `painel.html` são projeções. Cada comando bem sucedido tenta regenerá-las. Se a projeção falhar, o recibo informa `projection_warning` e a transação já confirmada permanece válida. Consulte `status` antes de repetir uma mutação cujo recibo se perdeu.

O painel é HTML local, sem script, rede, daemon ou atualização automática. A publicação é serializada com escritores do ledger; `projecoes.json` marca revisão e hashes para detectar geração parcial ou antiga. Gere novamente para conferir validade. Pode ser aberto no navegador ou no painel de arquivos, conforme suporte do host.

`checkpoint` faz backup consistente do banco SQLite, exporta JSON sem tokens de posse e gera manifesto com SHA256 e revisão. O backup inclui eventos. Ele não copia arquivos do produto nem desfaz ações. Para rollback do produto, use o mecanismo pertinente, como Git ou cópia explícita, dentro da autorização existente. Se o banco ativo se perder, preserve o estado restante, confira um backup com `doctor` em workspace separado e retome com reservas expiradas ou liberadas. Não troque o banco ativo durante execução concorrente.

`doctor` checa integridade SQLite e conta eventos. Isso não certifica o produto. Evite segredos nos textos e anexos. O ledger mantém os dados inseridos e não faz sanitização automática de informações privadas. `context`, `resume --full` e o helper de artefatos estão descritos em [economia.md](economia.md). O checkpoint do ledger continua com escopo de estado do processo; não inclui o catálogo/blobs de artefatos.
