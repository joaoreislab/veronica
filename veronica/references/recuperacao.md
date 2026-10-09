# Diagnóstico e recuperação sob demanda

Python 3.10+, biblioteca padrão e disco local com bloqueio SQLite confiável. Nos exemplos, `python`, `SKILL`, `PROJETO` e `NOVO_WORKSPACE` representam caminhos reais. Estabilize os escritores do produto e coordene o destino antes de diagnóstico profundo ou transferência. Use esses comandos em falhas, auditorias ou migrações que os exijam.

## Diagnóstico

```text
python SKILL/scripts/veronica.py --workspace PROJETO doctor --deep
python SKILL/scripts/preserve.py --workspace PROJETO reconcile
python SKILL/scripts/preserve.py --workspace PROJETO reconcile --repair
```

`doctor` confere SQLite e conta eventos. `--deep` também confere formas dos dados, tipos, referências, ciclos de dependências, relação entre revisão/eventos, catálogo e geração das projeções. Não repara, não abre aplicações e não certifica qualidade do produto. Em dados legados inválidos, preserve o banco e investigue os campos apontados.

`reconcile` verifica hashes/tamanhos, origens, recibos e uso observado. A consulta não cria catálogo nem apaga dados. `--repair` recataloga somente capturas com recibo válido e blob íntegro; repetir não duplica a origem. Um blob antigo sem recibo fica preservado, com origem desconhecida apontada para investigação. Recibos são arquivos locais de recuperação, não assinaturas de autenticidade. Interrupção antes da promoção pode deixar recibo sem blob; isso é informado sem inventar dados.

A restauração individual escreve e confere um temporário antes da promoção sem sobrescrita. Usa hard links, suportados no NTFS local testado; filesystem sem esse recurso recusa a promoção. Falha de cópia remove apenas o temporário próprio, permitindo nova tentativa no destino original.

As três projeções são publicadas sob exclusão com escritores do ledger. `projecoes.json` marca revisão e hashes; interrupção entre arquivos é detectável. Regenere com `dashboard`. O banco continua sendo a fonte canônica. A geração não congela mudanças posteriores nos arquivos de evidência ou passagem de prazos.

## Pacote para outro workspace

```text
python SKILL/scripts/recovery.py bundle --workspace PROJETO --output outputs/recuperacao-001 --include outputs/entrega
python SKILL/scripts/recovery.py verify --bundle CAMINHO_ABSOLUTO_DO_PACOTE
python SKILL/scripts/recovery.py restore --bundle CAMINHO_ABSOLUTO_DO_PACOTE --workspace NOVO_WORKSPACE
```

`bundle` cria pasta nova com backup SQLite do ledger, catálogo existente, blobs, recibos e arquivos do produto selecionados por `--include`. A opção pode se repetir. Sem ela, nenhum arquivo do produto é copiado. `bundle.json` enumera arquivos, hashes, revisão e escopo. Não selecionar workspace inteiro ou estado como produto. Aplicações, serviços, login e recursos externos não são transferidos. Escolha os dados da entrega antes de compartilhar o pacote.

Os escritores cooperantes do ledger e catálogo ficam bloqueados durante a fotografia. Arquivos do produto exigem estabilidade do produtor; igualdade de hashes não garante uma transação conjunta com aplicações externas. O pacote exige catálogo reconciliado e valida seus arquivos antes da promoção. Não altera o workspace de origem.

`verify` compara manifesto, hashes, integridade SQLite, formas do estado e catálogo. `restore` exige workspace inexistente e valida novamente a cópia antes da promoção. Expira reservas, registra a importação e regenera projeções. Preserva efeitos externos incertos: consulte o destino antes de repetir a ação. Evidência de arquivo não incluído continua desatualizada.

Para validar a retomada do objetivo, restaure em workspace separado, execute `status` e confira arquivos, pendências, ferramentas e critérios aplicáveis. Integridade do pacote, sozinha, não comprova prontidão do ambiente.
