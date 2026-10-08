# Veronica, um Ruflo otimizado?

**Uma skill para conduzir trabalhos longos com IA e preservar o próximo passo, gestão de agentes, autonomia de planejamento e execução milimetrica do inicio ao fim**

Estado salvo, dependências, retomada e evidências de conclusão em um núcleo local de Python e SQLite.

Quando um projeto atravessa várias sessões, o trabalho precisa de um lugar para guardar decisões, pendências e o que foi realmente verificado. Veronica fornece instruções e um helper local para registrar esse processo no workspace.

## O que ela faz

| Capacidade | Aplicação |
|---|---|
| Estado persistente | Guarda objetivo, tarefas, decisões e eventos em disco. |
| Retomada | Gera `RETOMAR.md` com situação e próxima ação. |
| Dependências | Organiza tarefas que precisam de entregas anteriores. |
| Conclusão com evidências | Exige registros atuais por critério e verifica hashes dos anexos declarados. |
| Reservas cooperativas | Registra executor, prazo e áreas de escrita para coordenação local. |
| Recuperação de falhas | Limita tentativas e pede mudança justificada de estratégia após falhas repetidas. |
| Efeitos externos incertos | Registra quando é necessário conferir o destino antes de repetir uma ação. |
| Painel e checkpoints | Produz HTML do estado e backups consistentes do registro do processo. |

O helper usa Python 3.10+ e SQLite da biblioteca padrão, sem dependências Python externas ou serviço residente. O assistente e as ferramentas usadas no projeto continuam sendo requisitos do ambiente.

## Para quem serve

- Pesquisas com várias fontes e entregas.
- Projetos de programação que atravessam sessões.
- Produção de relatórios, planilhas e apresentações.
- Trabalhos com etapas dependentes e verificações diferentes.
- Continuação de projetos interrompidos.

Tarefas pequenas podem seguir diretamente, sem criar um banco de projeto.

## Como começar

O pacote da skill fica em [`veronica/`](veronica/SKILL.md). No Codex, ele pode ser instalado como uma skill pessoal, no diretório de skills do seu ambiente. A pasta instalada deve manter o nome `veronica` e conter `SKILL.md`, `agents/`, `scripts/` e `references/`.

Em uma conversa que carregue a skill, peça:

> Use $veronica para conduzir este projeto, dividir as entregas, registrar as verificações e preservar o próximo passo.

Para continuar:

> Use $veronica para retomar o trabalho neste workspace e conferir o que falta.

O assistente precisa ter acesso ao workspace e às ferramentas necessárias. Para operar o helper diretamente, consulte o [guia de operação](veronica/references/operacao.md). Para usos concretos, veja os [exemplos](docs/EXEMPLOS.md).

## Estrutura

```text
README.md                     apresentação pública
CONTRIBUTING.md               como propor melhorias
docs/EXEMPLOS.md              situações de uso
veronica/
  SKILL.md                   instruções do assistente
  agents/openai.yaml         metadados da skill no Codex
  scripts/veronica.py        núcleo local de estado
  scripts/test_veronica.py   testes do helper
  references/               guias de operação e avaliação
```

Durante o uso, o estado do projeto fica no workspace, em `work/veronica/`. O conteúdo desse diretório pertence ao projeto em execução e não faz parte deste pacote de distribuição.

## Veronica e Ruflo

Veronica foi escrita como implementação própria. Sua pesquisa de desenho incluiu [Ruflo](https://github.com/ruvnet/ruflo), [Superpowers](https://github.com/obra/superpowers), Planning with Files, GSD e outros projetos.

Ruflo oferece uma plataforma ampla de coordenação de agentes e ferramentas. Veronica concentra seu escopo em instruções de trabalho e um registro local do processo. Ela pode ajudar um assistente a coordenar executores disponíveis quando a sessão permitir, mas seu helper não inicia agentes ou MCPs.

Não há comparação de desempenho, consumo de tokens ou produtividade contra Ruflo. Consulte as [fontes e decisões de desenho](veronica/references/origens.md) para entender as adaptações.

## Validação e limites

Na validação local da versão 1.0.0, os 14 testes do helper passaram no Windows. Eles cobrem invariantes de persistência, reservas, concorrência, evidências, retomada e recuperação. Isso não demonstra ganho geral de produtividade ou compatibilidade completa com todos os ambientes.

Para executar os testes a partir da raiz do repositório:

```sh
python veronica/scripts/test_veronica.py
```

Os registros de evidência descrevem verificações feitas pelo executor: o helper não julga a qualidade semântica de um teste ou de uma fonte. Hashes cobrem apenas os arquivos declarados. Reservas são cooperativas. Checkpoints preservam o estado do processo e não copiam os arquivos do produto. A skill depende da execução do assistente e não continua trabalhando depois que o host encerra a sessão.

## Participar

Veja [CONTRIBUTING.md](CONTRIBUTING.md). Melhorias podem partir de um caso real, um erro reproduzível ou uma comparação de método com resultados observados.

## Licença

A licença desta candidata de publicação ainda será definida antes do lançamento público.
