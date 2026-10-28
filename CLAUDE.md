# Naicas

App Django multi-unidade para a rede de escolas Naica: oficinas, cadastro de alunos em 6 etapas, matrícula e ficha de frequência, com 3 níveis de acesso (Diretor / Coordenador / Monitor).

As regras e decisões do projeto ficam neste arquivo. Leia antes de implementar qualquer coisa.

## Regras obrigatórias

- **Este arquivo é a memória do projeto e deve estar sempre atualizado.** Ao terminar QUALQUER alteração (funcionalidade, correção, ajuste visual, decisão do usuário, mudança de infra), antes do commit:
  1. acrescente uma entrada no topo de **Histórico** (data, o que foi feito, decisões tomadas e o porquê);
  2. atualize as seções afetadas (**Estado atual**, **Regras obrigatórias**, **Rodando local**, **Pendências**);
  3. inclua o `CLAUDE.md` no mesmo commit da alteração.
  Sem essa atualização a tarefa não está concluída.

- **Mais de uma pessoa trabalha neste repositório** (ex.: Isaque Miranda). Antes de começar qualquer tarefa: `git pull` (e veja o Histórico abaixo para saber o que mudou). Se o push for recusado, **nunca force**: faça `git fetch`, veja o que chegou e mescle, perguntando ao usuário quando houver trabalho conflitante.
- **Toda funcionalidade é um app Django próprio.** `naicas/` só tem settings/urls/wsgi/asgi. Funcionalidade que não cabe em app existente → app novo, registrado em `LOCAL_APPS` e incluído em `naicas/urls.py` com namespace.
- **Spec driven development:** se faltar informação para implementar (campo, regra, permissão, fluxo), perguntar ao usuário antes de codar e registrar a decisão aqui no CLAUDE.md.
- **Regra de ouro de escopo:** `Profile.escola` setada sempre vence `nivel_acesso` ao decidir a unidade ativa.
- **`escola = None` NÃO é Diretor:** Monitores são globais (também sem escola) e escopados pelas oficinas designadas (`Oficina.monitores`). Acesso de rede só com `nivel_acesso == 'DIRETOR'` ou superuser.
- Só o Diretor gerencia contas de usuário.
- **Dashboard** (app `dashboard`): só Diretor e Coordenador; é a primeira página depois do login para os dois (Monitor continua indo para o Início; `?next=` tem prioridade) e o destino padrão ao trocar de unidade. Respeita o recorte: visão geral = rede inteira + tabela por unidade; unidade em foco ou Coordenador = só a unidade. Indicadores sempre a partir de `acesso.filtrar_por_escola`/`visiveis_para`. Meta de frequência 75% (`indicadores.META_FREQUENCIA`), risco só com ≥3 chamadas. O "Início" continua existindo para todos.
- **Escala:** monitor ↔ oficina é `oficinas.Designacao` (dias vazio = todos os dias da oficina); as telas ficam no app `escalas` (agenda semanal padrão, aba por monitor, editor por monitor, "Minha semana"). Diretor (rede ou unidade em foco) e Coordenador (só a própria unidade) montam a escala; choque de horário é recusado mesmo entre unidades. A escala só orienta: o monitor designado lança chamada na oficina em qualquer dia. Choque de horário (matrícula e escala) é sempre `oficinas/horarios.py`.
- Diretor/admin pode "entrar" numa unidade (`escolas/foco.py`, sessão): filtros usam `acesso.filtrar_por_escola`/`visiveis_para`, que já respeitam o foco. Use sempre essas funções; nunca filtre por `Profile.escola` direto.
- **Dependência entre apps numa direção só:** `alunos` não importa `anexos`/`matriculas`; esses apps registram a sua etapa do cadastro em `alunos/etapas.py` no `ready()`.
- `/media/` nunca é servido diretamente: anexos (PII) só saem pela view `anexos:arquivo`.
- Escopo por unidade é aplicado no queryset/na view (mixins do `core`), nunca só escondido no template. O mesmo vale para os dados de saúde (LGPD).
- Templates em `<app>/templates/<app>/`, sempre estendendo `core/base.html` (Bootstrap 5.3 + bootstrap-icons).
- Textos de interface, nomes de models e campos em português.
- **Identidade visual** em `core/static/core/naicas.css` ("material de escola"): tokens anil `#2b3a8c`, urucum `#c8471f`, ipê `#f2b705`, folha `#2e7a4c`, papel `#f3f4f8`, grafite `#1e2230`; fonte Lexend no app todo. A **fita crepe** (`.fita`, fonte Kalam) é a assinatura e só marca "onde você está" (unidade na barra, login): não espalhar. Cargos na barra (`.cargo-diretor` ipê, `.cargo-coordenador` `#9ad7b0`, `.cargo-monitor` `#f6b195`): usar as mesmas cores sempre que o cargo aparecer. Use as classes do Bootstrap normalmente; as cores já vêm sobrescritas pelas variáveis.

## Estado atual

MVP completo + escala dos monitores + dashboard. Repositório: `github.com/rdssystems/Naicas-django` (privado, branch `main`). 10 apps locais (`core`, `escolas`, `usuarios`, `oficinas`, `alunos`, `anexos`, `matriculas`, `frequencia`, `escalas`, `dashboard`); PostgreSQL 16 no Docker; Django 5.2.17 em Python 3.12. Dados de demonstração: `popular_demo` (carga grande por unidade) ou `popular_alunos` (ver Rodando local).

| App | O que tem |
|---|---|
| `core` | Regras de acesso (`acesso.py`), middleware da unidade ativa, mixins de permissão, `base.html`, página inicial de atalhos, CSS da identidade, favicon |
| `escolas` | `EscolaNaica` (10 unidades de Uberlândia via migração), CRUD do Diretor, "entrar na unidade" (`foco.py`) |
| `usuarios` | `Profile` (Diretor/Coordenador/Monitor), login, CRUD de contas (só Diretor) |
| `oficinas` | `TipoOficina` (por unidade), `Oficina` (dias, horário, status manual), `Designacao` (monitor × oficina × dias), `horarios.py` (choque) |
| `alunos` | Cadastro em etapas: dados+endereço, responsáveis (reaproveitados por CPF), família/emergência, saúde (LGPD); registro de etapas e de visibilidade |
| `anexos` | Tipos de documento (Diretor), envio PDF/imagem validado, download só por view autenticada (etapa 5) |
| `matriculas` | Matrícula com vagas, choque de horário, concluir/desistência (etapa 6) |
| `frequencia` | Chamada P/F/J por data, resumo com % por aluno |
| `escalas` | Agenda semanal, grade por monitor, editor da escala, "Minha semana" |
| `dashboard` | Painel do Diretor/Coordenador: operação de hoje, números-chave, frequência semanal (gráfico SVG), risco de evasão, ocupação, pendências de cadastro e, na visão geral, a tabela por unidade (`indicadores.py`, `grafico.py`) |

### Pendências e decisões em aberto
- **Tipo de oficina:** remover (A) ou virar lista única da rede, opcional (B)? Aguardando o usuário.
- **LGPD do Monitor:** o que ele vê da ficha de saúde (mudar só `core.acesso.pode_ver_saude_emergencia`).
- **Deploy na VPS** (Tailscale + `tailscale serve` para HTTPS), backup do banco e dos anexos, SSO Keycloak.
- O acesso pela rede local (celular/Mac) foi testado e **descartado** pelo usuário em 2026-10-26.

## Rodando local

```bash
docker compose up -d --build      # app em http://localhost:8020
docker compose exec web python manage.py test
docker compose exec web python manage.py createsuperuser
docker compose logs -f web
docker compose exec web python manage.py popular_alunos [--quantidade 10] [--escola <slug>] [--seed 42]  # alunos fictícios com cadastro completo (só DEBUG)
docker compose exec web python manage.py popular_anexos --ficticios   # PDFs fictícios nos obrigatórios pendentes (só DEBUG)
docker compose exec web python manage.py popular_demo [--seed 2026]   # 30 alunos, 5 oficinas, matrículas e chamadas por unidade (só DEBUG; uma execução)
```

- Testes sempre pelo serviço `web` (`docker compose exec web python manage.py test`): fora do Docker o host `db` do Postgres não resolve.
- Portas: web `8020`, Postgres `127.0.0.1:5436` (8000/5434 são do Gestão Qualificação).
- `.env` (não versionado) vem do `.env.example`. Com `DEBUG=True` o container usa `runserver`; com `DEBUG=False`, Gunicorn.
- Alterou `settings.py`? `docker compose restart web`. Alterou o `.env`? `docker compose up -d --force-recreate web` (o `restart` não relê o `.env`).
- **Acesso por outros aparelhos (celular na mesma rede / Tailscale):** `WEB_BIND=0.0.0.0` no `.env` e o IP da máquina em `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` (com `http://` e a porta). Se o IP do Wi-Fi mudar, atualize os dois e recrie o container. O padrão (`127.0.0.1`) só aceita a própria máquina: é o que deve ficar na VPS.

## Deploy

`atualizar.sh` na VPS: backup opcional → `git reset --hard origin/main` → `docker compose up -d --build` → healthcheck com header `Host` = `HEALTHCHECK_HOST`. Domínio/VPS só serão definidos após o MVP.

## Histórico

Mais recente primeiro. Toda alteração entra aqui (ver primeira regra obrigatória).

- **2026-10-28** — Regra nova: `git pull` antes de começar qualquer tarefa e nunca forçar push, depois do trabalho em paralelo no dashboard (meu e do Isaque) que precisou de mesclagem.
- **2026-10-28** — **Mesclagem com o commit do Isaque Miranda** (dashboard paralelo + dados de demonstração). Decisão do usuário: fica o dashboard completo (indicadores escolhidos, escopo via `visiveis_para`, frequência (P+J), 16 testes); aproveitados do Isaque o `popular_demo`, o `.gitignore` ampliado e o histórico. `.env.example` voltou a documentar todas as variáveis (mantidos `DB_HOST`/`DB_PORT`). `LOGIN_REDIRECT_URL` voltou a `core:home` (Diretor/Coordenador vão ao Dashboard pela `LoginView`).
- **2026-10-28** — **Dashboard** (app novo `dashboard`) para Diretor e Coordenador, primeiro item da barra e primeira página após o login (decisão do usuário: Monitor segue no Início, que continua existindo). Indicadores escolhidos pelo usuário: operação de hoje (chamadas pendentes, oficinas sem monitor), alunos (total, incompletos e o que falta, fila de espera), matrículas e ocupação (lotadas), frequência (30 dias, gráfico das 8 semanas com meta 75%, alunos abaixo da meta). Visão geral do Diretor ganha a tabela por unidade com botão "Entrar"; trocar de unidade agora volta ao Dashboard. `alunos.etapas.etapas_pendentes()` adicionado.
- **2026-10-28** — `.gitignore` ampliado para ambientes locais, overrides de Docker Compose e artefatos de cobertura/análise Python, preservando `.env.example` e arquivos de implementação no versionamento.
- **2026-10-28** — Criado `popular_demo`, comando somente para desenvolvimento, para carregar em cada Naica 30 alunos fictícios, cinco oficinas, duas matrículas por aluno e quatro chamadas por oficina com presença/falta/justificada simuladas. A carga é transacional e recusa duplicação.
- **2026-10-28** — Carga `popular_demo --seed 2026` executada no banco local de quem rodou o comando (Isaque): 10 Naicas, 300 alunos, 50 oficinas, 600 matrículas e chamadas simuladas.
- **2026-10-28** — (Isaque, substituído na mesclagem pelo dashboard acima) Criado o app `dashboard`, incluído na navbar e definido como destino pós-login de Diretor e Coordenador. Indicadores de alunos, oficinas em atividade, matrículas cursando e presença respeitam a unidade ativa; Diretor sem foco também vê resumo por Naica e pode entrar na unidade. Monitor mantém a página inicial de atalhos.
- **2026-10-28** — Revisão inicial do projeto: confirmados os 9 apps locais, a arquitetura de etapas registrada por `ready()`, o escopo aplicado em queryset/view e o PostgreSQL 16 via Docker. Corrigida a descrição que dizia “8 apps”. `manage.py check` passou; a suíte identificou 212 testes, mas ficou impedida fora do Compose porque o host `db` não estava disponível.
- **2026-10-28** — Adicionado arquivo `.env.example` e ajustada a configuração do ambiente Docker local para desenvolvimento (resolução de conexão com o banco e variáveis de ambiente).
- **2026-10-26** — `CLAUDE.md` vira a memória do projeto: regra de atualizá-lo a cada alteração, seções "Estado atual" e "Histórico".
- **2026-10-26** — Spec `naicas_prompt_espinha_dorsal.md` removido **de propósito** pelo usuário; decisões passam a ser registradas aqui.
- **2026-10-26** — Projeto publicado no GitHub (`rdssystems/Naicas-django`, privado). Histórico auditado: nenhum segredo commitado.
- **2026-10-26** — Superuser de teste `isaque` criado no banco de dev (não existe em produção). Testes de acesso pela rede local descartados.
- **2026-10-07** — **Escala dos monitores**: `Designacao` com dias por monitor (oficina pode ser dividida), choque recusado inclusive entre unidades, Diretor e Coordenador montam, escala só orienta a chamada. **Agenda semanal** (dias × horas, blocos lado a lado, "sem monitor" tracejado, filtro por monitor) + aba "Por monitor" + "Minha semana".
- **2026-10-07** — Tipos de oficina saíram de "Configurações" e viraram botão na página de Oficinas; login com "Secretaria de Desenvolvimento Social"; 10 unidades reais cadastradas por migração.
- **2026-10-07** — Identidade visual "material de escola" (anil/urucum/ipê/folha, Lexend, fita crepe com o nome da unidade); etiqueta do cargo na barra; chamada otimizada para celular; `WEB_BIND` no compose (padrão só local).
- **2026-10-07** — Favicon; Diretor/admin pode "entrar" numa unidade ou ver a rede inteira (nome da unidade na barra).
- **2026-10-02** — Frequência (chamada P/F/J, % por aluno). **MVP completo.**
- **2026-10-02** — Matrícula (vagas com trava, choque de horário, matrícula por CPF entre unidades).
- **2026-10-02** — Anexos (PDF/imagem, obrigatórios bloqueiam o selo "completo"); etapas do cadastro viram registro.
- **2026-10-02** — Cadastro do aluno: dados/endereço (ViaCEP), responsáveis por CPF, família/emergência (parentesco em lista única), ficha de saúde (LGPD).
- **2026-10-02** — Oficinas e tipos por unidade; monitores globais.
- **2026-10-02** — Fundação: unidades, perfis Diretor/Coordenador/Monitor, login, regras de acesso.
- **2026-10-01** — Estrutura inicial (8 apps, Docker Compose, `atualizar.sh`).
