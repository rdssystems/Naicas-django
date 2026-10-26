# Naicas

App Django multi-unidade para a rede de escolas Naica: oficinas, cadastro de alunos em 6 etapas, matrícula e ficha de frequência, com 3 níveis de acesso (Diretor / Coordenador / Monitor).

As regras e decisões do projeto ficam neste arquivo. Leia antes de implementar qualquer coisa.

## Regras obrigatórias

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
