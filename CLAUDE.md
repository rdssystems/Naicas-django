# Naicas

App Django multi-unidade para a rede de escolas Naica: oficinas, cadastro de alunos em 6 etapas, matrícula e ficha de frequência, com 3 níveis de acesso (Diretor / Coordenador / Monitor).

**Fonte de verdade da especificação:** [naicas_prompt_espinha_dorsal.md](naicas_prompt_espinha_dorsal.md). Leia antes de implementar qualquer coisa.

## Regras obrigatórias

- **Toda funcionalidade é um app Django próprio** (seção 2.1 do spec). `naicas/` só tem settings/urls/wsgi/asgi. Funcionalidade que não cabe em app existente → app novo, registrado em `LOCAL_APPS` e incluído em `naicas/urls.py` com namespace.
- **Spec driven development:** se faltar informação para implementar (campo, regra, permissão, fluxo), perguntar ao usuário antes de codar e registrar a decisão no spec (seção 2.2 ou checklist da seção 6).
- **Regra de ouro de escopo:** `Profile.escola` setada sempre vence `nivel_acesso` ao decidir a unidade ativa.
- **`escola = None` NÃO é Diretor:** Monitores são globais (também sem escola) e escopados pelas oficinas designadas (`Oficina.monitores`). Acesso de rede só com `nivel_acesso == 'DIRETOR'` ou superuser.
- Só o Diretor gerencia contas de usuário.
- Diretor/admin pode "entrar" numa unidade (`escolas/foco.py`, sessão): filtros usam `acesso.filtrar_por_escola`/`visiveis_para`, que já respeitam o foco. Use sempre essas funções; nunca filtre por `Profile.escola` direto.
- **Dependência entre apps numa direção só:** `alunos` não importa `anexos`/`matriculas`; esses apps registram a sua etapa do cadastro em `alunos/etapas.py` no `ready()`.
- `/media/` nunca é servido diretamente: anexos (PII) só saem pela view `anexos:arquivo`.
- Escopo por unidade é aplicado no queryset/na view (mixins do `core`), nunca só escondido no template. O mesmo vale para os dados de saúde (LGPD).
- Templates em `<app>/templates/<app>/`, sempre estendendo `core/base.html` (Bootstrap 5.3 + bootstrap-icons).
- Textos de interface, nomes de models e campos em português.

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
- Alterou `settings.py` ou `.env`? Reinicie o container (`docker compose restart web`).

## Deploy

`atualizar.sh` na VPS: backup opcional → `git reset --hard origin/main` → `docker compose up -d --build` → healthcheck com header `Host` = `HEALTHCHECK_HOST`. Domínio/VPS só serão definidos após o MVP.
