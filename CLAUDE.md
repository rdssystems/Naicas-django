# Naicas

App Django multi-unidade para a rede de escolas Naica: oficinas, cadastro de alunos em 6 etapas, matrícula e ficha de frequência, com 3 níveis de acesso (Diretor / Coordenador / Monitor).

As regras e decisões do projeto ficam neste arquivo. Leia antes de implementar qualquer coisa.

## Regras obrigatórias

- **Este arquivo é a memória do projeto e deve estar sempre atualizado.** Ao terminar QUALQUER alteração (funcionalidade, correção, ajuste visual, decisão do usuário, mudança de infra), antes do commit:
  1. acrescente uma entrada no topo de **Histórico** (data, o que foi feito, decisões tomadas e o porquê);
  2. atualize as seções afetadas (**Estado atual**, **Regras obrigatórias**, **Rodando local**, **Pendências**);
  3. inclua o `CLAUDE.md` no mesmo commit da alteração.
  Sem essa atualização a tarefa não está concluída.

- **Toda funcionalidade é um app Django próprio.** `naicas/` só tem settings/urls/wsgi/asgi. Funcionalidade que não cabe em app existente → app novo, registrado em `LOCAL_APPS` e incluído em `naicas/urls.py` com namespace.
- **Spec driven development:** se faltar informação para implementar (campo, regra, permissão, fluxo), perguntar ao usuário antes de codar e registrar a decisão aqui no CLAUDE.md.
- **Regra de ouro de escopo:** `Profile.escola` setada sempre vence `nivel_acesso` ao decidir a unidade ativa.
- **`escola = None` NÃO é Diretor:** Monitores são globais (também sem escola) e escopados pelas oficinas designadas (`Oficina.monitores`). Acesso de rede só com `nivel_acesso == 'DIRETOR'` ou superuser.
- Só o Diretor gerencia contas de usuário.
- **Escala:** monitor ↔ oficina é `oficinas.Designacao` (dias vazio = todos os dias da oficina); as telas ficam no app `escalas` (agenda semanal padrão, aba por monitor, editor por monitor, "Minha semana"). Diretor (rede ou unidade em foco) e Coordenador (só a própria unidade) montam a escala; choque de horário é recusado mesmo entre unidades. A escala só orienta: o monitor designado lança chamada na oficina em qualquer dia. Choque de horário (matrícula e escala) é sempre `oficinas/horarios.py`.
- Diretor/admin pode "entrar" numa unidade (`escolas/foco.py`, sessão): filtros usam `acesso.filtrar_por_escola`/`visiveis_para`, que já respeitam o foco. Use sempre essas funções; nunca filtre por `Profile.escola` direto.
- **Dependência entre apps numa direção só:** `alunos` não importa `anexos`/`matriculas`; esses apps registram a sua etapa do cadastro em `alunos/etapas.py` no `ready()`.
- `/media/` nunca é servido diretamente: anexos (PII) só saem pela view `anexos:arquivo`.
- Escopo por unidade é aplicado no queryset/na view (mixins do `core`), nunca só escondido no template. O mesmo vale para os dados de saúde (LGPD).
- Templates em `<app>/templates/<app>/`, sempre estendendo `core/base.html` (Bootstrap 5.3 + bootstrap-icons).
- Textos de interface, nomes de models e campos em português.
- **Identidade visual** em `core/static/core/naicas.css` ("material de escola"): tokens anil `#2b3a8c`, urucum `#c8471f`, ipê `#f2b705`, folha `#2e7a4c`, papel `#f3f4f8`, grafite `#1e2230`; fonte Lexend no app todo. A **fita crepe** (`.fita`, fonte Kalam) é a assinatura e só marca "onde você está" (unidade na barra, login): não espalhar. Cargos na barra (`.cargo-diretor` ipê, `.cargo-coordenador` `#9ad7b0`, `.cargo-monitor` `#f6b195`): usar as mesmas cores sempre que o cargo aparecer. Use as classes do Bootstrap normalmente; as cores já vêm sobrescritas pelas variáveis.

## Estado atual

MVP completo + escala dos monitores. Repositório: `github.com/rdssystems/Naicas-django` (privado, branch `main`).

| App | O que tem |
|---|---|
| `core` | Regras de acesso (`acesso.py`), middleware da unidade ativa, mixins de permissão, `base.html`, painel inicial, CSS da identidade, favicon |
| `escolas` | `EscolaNaica` (10 unidades de Uberlândia via migração), CRUD do Diretor, "entrar na unidade" (`foco.py`) |
| `usuarios` | `Profile` (Diretor/Coordenador/Monitor), login, CRUD de contas (só Diretor) |
| `oficinas` | `TipoOficina` (por unidade), `Oficina` (dias, horário, status manual), `Designacao` (monitor × oficina × dias), `horarios.py` (choque) |
| `alunos` | Cadastro em etapas: dados+endereço, responsáveis (reaproveitados por CPF), família/emergência, saúde (LGPD); registro de etapas e de visibilidade |
| `anexos` | Tipos de documento (Diretor), envio PDF/imagem validado, download só por view autenticada (etapa 5) |
| `matriculas` | Matrícula com vagas, choque de horário, concluir/desistência (etapa 6) |
| `frequencia` | Chamada P/F/J por data, resumo com % por aluno |
| `escalas` | Agenda semanal, grade por monitor, editor da escala, "Minha semana" |

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
```

- Portas: web `8020`, Postgres `127.0.0.1:5436` (8000/5434 são do Gestão Qualificação).
- `.env` (não versionado) vem do `.env.example`. Com `DEBUG=True` o container usa `runserver`; com `DEBUG=False`, Gunicorn.
- Alterou `settings.py`? `docker compose restart web`. Alterou o `.env`? `docker compose up -d --force-recreate web` (o `restart` não relê o `.env`).
- **Acesso por outros aparelhos (celular na mesma rede / Tailscale):** `WEB_BIND=0.0.0.0` no `.env` e o IP da máquina em `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` (com `http://` e a porta). Se o IP do Wi-Fi mudar, atualize os dois e recrie o container. O padrão (`127.0.0.1`) só aceita a própria máquina: é o que deve ficar na VPS.

## Deploy

`atualizar.sh` na VPS: backup opcional → `git reset --hard origin/main` → `docker compose up -d --build` → healthcheck com header `Host` = `HEALTHCHECK_HOST`. Domínio/VPS só serão definidos após o MVP.

## Histórico

Mais recente primeiro. Toda alteração entra aqui (ver primeira regra obrigatória).

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
