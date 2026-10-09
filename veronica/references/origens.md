# Decisões de desenho e fontes

Implementação própria, sem copiar código dos repositórios pesquisados. Nenhum framework da pesquisa é dependência obrigatória. Fontes serviram para escolher mecanismos e evitar promessas excessivas.

| Mecanismo | Referência de pesquisa | Adaptação na Veronica |
|---|---|---|
| Estado em disco e próximo passo | [Planning with Files](https://github.com/OthmanAdi/planning-with-files), [GSD](https://github.com/open-gsd/gsd-core) | Banco local transacional e resumo legível |
| Conclusão por evidência | [Superpowers](https://github.com/obra/superpowers) | Critérios e registros por tentativa, com hashes e prazo |
| Contexto sob demanda | [Context Engineering](https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering), [ECC](https://github.com/affaan-m/ECC) | Entrada curta e referências condicionais |
| Reserva e orçamento | [Ruflo](https://github.com/ruvnet/ruflo), [Agent Orchestra](https://github.com/3338902669-ops/agent-orchestra) | Reserva cooperativa com token, prazo e limite de concorrência |
| Falhas repetidas | [Ralph](https://github.com/frankbria/ralph-claude-code) | Assinatura de erro e mudança de estratégia com histórico |
| Efeito ambíguo | [Faultbench](https://github.com/mit-hun-k/faultbench), [TanStack Workflow](https://github.com/TanStack/workflow) | Reconciliação explícita antes de repetir |
| Comparação do método | [SkillEvaluator](https://github.com/NVIDIA/SkillEvaluator), [SkillsBench](https://github.com/benchflow-ai/skillsbench) | Plano de avaliação e limites do que foi demonstrado |

SQLite substitui vários arquivos mutáveis porque reserva, tentativa e evento precisam confirmar juntos entre processos locais. O agregado de projeto é propositalmente pequeno. Não há banco remoto, memória vetorial ou serviço permanente.

Uma skill depende do runtime para ferramentas, agentes e continuidade. Mesmo com ledger persistente, ela não trabalha depois de o host encerrar a execução. Automação recorrente, replay de modelo, indexação semântica e mapas de código podem ser extensões futuras, se houver necessidade e validação.

## Economia preservando dados — versão 1.1

Inspeção dirigida de fontes abertas em versões fixadas. Implementação nova própria, sem incorporar arquivos ou instalar frameworks. Referências de estruturas e limites:

- [rtk-ai/rtk — src/core/tee.rs](https://github.com/rtk-ai/rtk/blob/e4f05094d613580b236e0ce1297eb32b998559fa/src/core/tee.rs).
- [mksglu/context-mode — src/store.ts](https://github.com/mksglu/context-mode/blob/51a716fd2be075fc71610f876f44ea6895b46970/src/store.ts).
- [snchimata/tokenfold — crates/tokenfold-core/src/codec.rs](https://github.com/snchimata/tokenfold/blob/b0a74da826632379c63150ab40a830ca7009f07c/crates/tokenfold-core/src/codec.rs).
- [KkSss999/pmem — src/context-pack/index.ts](https://github.com/KkSss999/pmem/blob/4c9c96dbd0c498cd4265e8729f197f3fe673a604/src/context-pack/index.ts).
- [Aider-AI/aider — aider/repomap.py](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py).
- [thedotmack/claude-mem — src/services/worker/search/strategies/SQLiteSearchStrategy.ts](https://github.com/thedotmack/claude-mem/blob/eccb15e755467a4e0697f168dd0123a6d24b2aca/src/services/worker/search/strategies/SQLiteSearchStrategy.ts).
- [NousResearch/hermes-agent — tools/file_operations_common.py](https://github.com/NousResearch/hermes-agent/blob/3b0dc776b6602b0dd05429d7842bb143d73434b7/tools/file_operations_common.py).
- [ccusage/ccusage — rust/adapters/codex/src/aggregate.rs](https://github.com/ccusage/ccusage/blob/2a4a7fce8cfe95c5100aff53627aae11a0556da9/rust/adapters/codex/src/aggregate.rs).

Não importar filtros lossy, omissões por budget, normalização de espaços/terminações, limites ocultos ou pressupostos de tokenização como uso real. Os novos mecanismos preservam snapshots, ordens e origens; visões e compactação são opcionais. Hash reutilizado apenas na mesma consulta de estado. A comparação local orienta seleção adaptativa; o conjunto completo não precisa ser acionado em toda tarefa.


