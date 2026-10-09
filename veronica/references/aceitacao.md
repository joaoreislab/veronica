# Critérios por domínio

Escolha verificações que discriminem conclusão de preparação. Nem toda tarefa precisa dos mesmos testes.

| Domínio | Critério útil | Evidência pertinente | Pendência que deve ficar explícita |
|---|---|---|---|
| Pesquisa | Perguntas respondidas com fonte e incerteza | Fonte primária aberta, trecho e data, limite de cobertura | Fonte inacessível, contradição ou hipótese |
| Documento | Conteúdo correto e apresentação utilizável | Conferência de dados e renderização quando a diagramação importa | Revisão visual ou humana ainda não feita |
| Software | Comportamento solicitado funciona | Execução e testes adequados, log e insumos anexados | Fluxo real não exercitado ou plataforma não testada |
| Apps e automação | Estado final observado no destino | Leitura atual da interface ou API, comparação antes/depois | Autenticação, ação física ou resultado externo incerto |
| Projeto criativo | Requisitos e experiência pretendida atendidos | Execução, inspeção visual e feedback do usuário quando exigido | Aprovação estética, física ou longa duração |

Um teste de unidade não prova experiência visual. Uma captura finita não demonstra estabilidade por horas. A existência de um arquivo não prova suas fórmulas, fontes ou funcionamento. Ajuste o critério à promessa da entrega e evite ampliar a validação sem razão.

Separe critérios em IDs independentes quando provas diferentes forem necessárias. Por exemplo, `conteudo` com tipo `file`, `execucao` com tipo `runtime` e `aprovacao` com tipo `human`. Se aprovação humana for requisito real, ela continua pendente até resposta recebida. Não invente aprovação extra para tarefa reversível que já foi autorizada.

Tipos são organização do ledger, não detectores automáticos de verdade. Evidência deve relatar observação positiva real, seu método e limitações. Registre faltas em `next`, `task.release` ou `task.fail`, sem convertê-las em sucesso.
