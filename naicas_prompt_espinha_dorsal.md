# Prompt — Espinha Dorsal do App Naicas (baseado na plataforma Gestão Qualificação Profissional)

> Como usar: cole este documento inteiro como prompt inicial numa sessão nova do Claude Code, dentro do repositório vazio do projeto Naicas. Ele descreve só o que será reaproveitado da plataforma de origem: a arquitetura multi-unidade com 3 níveis de acesso, e o modelo de login, oficinas, inscrição, matrícula e ficha de frequência. Tudo mais da plataforma original (score socioeconômico, documentos, declaração, relatórios por e-mail, painel de TV, treinamento, WhatsApp) fica de fora — não existe no Naicas.

## 1. Objetivo

Construir um novo app Django para o **Naicas**: múltiplas escolas/unidades Naica, cada uma com suas próprias oficinas, seus próprios alunos e seus próprios usuários com acesso restrito à própria unidade — exatamente o padrão multi-tenant já validado em produção na plataforma de origem, só que com nomenclatura de oficina em vez de curso.

## 2. Stack obrigatória (idêntica à plataforma de origem)

- **Django 5.2** / **Python 3.12**
- **PostgreSQL 16** como banco principal
- **Docker Compose** para orquestrar `db` (Postgres) e `web` (Django), com o código em bind-mount (`.:/app`) para permitir deploy só com `git pull` + rebuild, sem rebuild de imagem base
- Deploy em VPS via **Docker Compose** + script de atualização (`atualizar.sh`) — ver seção 5
- Sem Redis/Channels/Daphne: o Naicas não tem painel em tempo real nem chamada pública sem login, então **WSGI puro (Gunicorn) é suficiente** — mais simples de manter que a origem

## 2.1 Regras de organização do código (obrigatórias)

1. **Toda funcionalidade é um app Django próprio.** Nada de colocar models/views de domínios diferentes no mesmo app, e nada de lógica de negócio dentro do pacote do projeto (`naicas/`), que só guarda `settings`, `urls` raiz, `wsgi` e `asgi`.
2. Funcionalidade nova que não se encaixa em nenhum app existente → **cria um app novo** (`python manage.py startapp <nome>`), registra em `INSTALLED_APPS` e inclui as URLs no `naicas/urls.py` com `namespace` próprio. Na dúvida se é app novo ou extensão de um existente, decidir junto antes de codar (spec driven).
3. Cada app é autocontido: `models.py`, `views.py`, `urls.py` (com `app_name`), `forms.py`, `admin.py`, `tests.py` e templates em `<app>/templates/<app>/`.
4. Dependência entre apps só em uma direção, e nunca de `core` para os apps de domínio: `core` é a base (middleware, mixins, `base.html`) e os outros apps importam dele, não o contrário.
5. Nomes de apps no plural e em português, minúsculos, sem acento.

### Mapa de apps

| App | Responsabilidade |
|---|---|
| `naicas/` | Pacote do projeto: settings, urls raiz, wsgi/asgi (sem lógica de negócio) |
| `core` | Middleware `active_escola`, mixins de permissão, `base.html`, página inicial/dashboard, utilidades compartilhadas |
| `escolas` | `EscolaNaica` |
| `usuarios` | `Profile`, Groups (Diretor/Coordenador/Monitor), login/logout, CRUD de usuários |
| `oficinas` | `TipoOficina`, `Oficina` |
| `alunos` | `Aluno`, `Endereco`, `Responsavel`, `AlunoResponsavel`, `MembroFamiliar`, `ContatoEmergencia`, `FichaSaude` e o wizard de cadastro em 6 etapas |
| `anexos` | `TipoDocumento`, `Anexo` |
| `matriculas` | `Matricula` |
| `frequencia` | `RegistroAula`, `Chamada` |

## 2.2 Decisões já tomadas

- **Interface:** Bootstrap 5.3 + bootstrap-icons via CDN, `django-widget-tweaks` nos forms, mesmo padrão visual da origem.
- **Portas locais:** web em `localhost:8020`, Postgres em `127.0.0.1:5436`, sem conflito com Gestão Qualificação (8000/5434), BelezaApp (8010) e Keycloak (8180).
- **SSO Keycloak:** fica para **depois do MVP**. Começa só com login usuário/senha, e o settings já é escrito para receber OIDC depois sem refatoração.
- **Domínio/VPS:** definido só quando houver MVP estável. Até lá, `ALLOWED_HOSTS` vem do `.env`.
- **Regra LGPD da `FichaSaude` para o Monitor:** adiada. Implementar como permissão isolada, fácil de ajustar depois.
- **Login:** por **nome de usuário** (`username`) + senha, igual à origem. Isso também facilita o vínculo com o SSO depois.
- **Criação e gestão de contas:** **só o Diretor** cria, edita, desativa e troca senha de usuários (Coordenadores e Monitores). Coordenador e Monitor não gerenciam contas.
- **Superuser** do Django é tratado como Diretor (acesso de rede).
- **Escolas Naica:** cadastradas numa tela própria do painel, acessível só ao Diretor (além do Django Admin).
- **Monitores são globais (da rede), não de uma unidade:** pela escala, o mesmo Monitor atende oficinas de unidades diferentes. A conta do Monitor tem `Profile.escola = None`, e o escopo dele é definido **pelas oficinas em que foi designado**, não por unidade.
- **Designação Monitor↔Oficina:** `Oficina.monitores` (M2M com usuários Monitor de qualquer unidade). Quem designa: o **Diretor** (qualquer oficina) e o **Coordenador** (escolhe da lista global de Monitores, mas só designa nas oficinas da própria unidade). É só um vínculo, sem período de vigência: trocar a escala é remover um Monitor e colocar outro. O histórico fica em `RegistroAula.lancado_por`.
- `nome_monitor`/`telefone_monitor` da `Oficina` continuam como texto livre para quem conduz a oficina sem ter conta no sistema.
- **Usuários não são excluídos, só desativados** (`is_active`), para preservar o histórico (ex.: `RegistroAula.lancado_por`). O Diretor não pode desativar a própria conta nem alterar o próprio nível.
- **Unidades não têm exclusão pelo painel** no MVP: elas vão concentrar oficinas, alunos e matrículas.
- **Regras de acesso centralizadas em `core/acesso.py`** (`NivelAcesso`, `is_diretor`, `filtrar_por_escola`, `pode_acessar_oficina`…). Middleware, mixins e todos os apps usam essas funções, sem reimplementar a regra.

## 3. Arquitetura multi-unidade + 3 níveis de acesso (o núcleo a replicar)

Cada registro pertence a uma **Escola Naica** (unidade física). A maior parte da lógica de permissão e filtragem de dados depende de **qual unidade o usuário logado enxerga** — exatamente como na plataforma de origem, trocando só os nomes dos papéis.

### Model `EscolaNaica`
- `nome`, `slug`, `endereco`, `telefone`, `email`
- `coordenador_user` (FK opcional para o responsável local)

### `Profile` (1:1 com `User`)
- `escola` (FK nullable para `EscolaNaica`) — **obrigatória para Coordenador** e **sempre `None` para Diretor e Monitor**
- `nivel_acesso` com 3 valores: **`DIRETOR`**, **`COORDENADOR`**, **`MONITOR`**
- Essa combinação é garantida no banco (`CheckConstraint`) e no `clean()` do model, não só no formulário

| `nivel_acesso` | `escola` | Escopo |
|---|---|---|
| `DIRETOR` | `None` | Rede inteira |
| `COORDENADOR` | obrigatória | Só a própria unidade |
| `MONITOR` | `None` | Só as oficinas em que está designado (`Oficina.monitores`), em qualquer unidade |

### Os 3 níveis de acesso

| Nível | Escopo | Equivalente na origem |
|---|---|---|
| **Diretor** | Vê e gerencia **todas** as unidades Naica (rede inteira). `Profile.escola = None`. | Admin de rede (`ADMIN_CP`/`ADMIN_UDITECH`) / superuser |
| **Coordenador de Unidade** | Só enxerga e gerencia a **própria** unidade (`Profile.escola` setada). Cria/edita oficinas, alunos, matrículas e frequência daquela unidade, e designa Monitores nas oficinas dela. Não gerencia contas. | `Coordenador` (grupo) |
| **Monitor** | Conta **global** (`Profile.escola = None`), escopada pelas **oficinas em que foi designado** (`Oficina.monitores`), que podem ser de unidades diferentes. Permissão restrita: só lança frequência (ficha de chamada) dessas oficinas e vê a lista de alunos matriculados nelas, sem editar cadastro de aluno nem gerenciar oficinas/usuários. | Papel novo — não existe equivalente direto na origem; antes era resolvido por link público sem login, aqui vira uma conta de verdade com permissão reduzida |

### Regra de ouro herdada da origem (já causou bug real em produção — não repetir)

Se o `Profile` tem uma `escola` vinculada, ela **sempre** tem prioridade sobre `nivel_acesso` em qualquer lugar do código que decida "qual unidade/tema usar agora" — nunca o contrário. Um Profile com `escola` setada E `nivel_acesso='DIRETOR'` ao mesmo tempo é um estado inconsistente que não deveria existir, mas se existir, a escola vinculada deve vencer sempre.

**Regra nova do Naicas: `escola = None` NÃO significa Diretor.** O Monitor também tem `escola = None`. Acesso de rede só existe quando `nivel_acesso == 'DIRETOR'` (ou superuser). Qualquer código que trate "sem escola" como "vê tudo" vaza a rede inteira para os Monitores. Esse caso deve ter teste explícito.

### Peças a replicar

- **Middleware de contexto** (equivalente ao `AdminContextMiddleware` da origem): calcula a cada request `request.active_escola` a partir do `Profile` do usuário logado. É a unidade do Coordenador; para Diretor e Monitor fica `None`. Para o Monitor, a unidade vem da oficina acessada (`oficina.escola`), nunca do `Profile`.
- **Mixins de permissão** (`core/mixins.py` na origem):
  - `DiretorRequiredMixin` — só passa quando `nivel_acesso == 'DIRETOR'` e `Profile.escola is None` (ou superuser).
  - `CoordenadorUnidadeRequiredMixin` — só passa quando `nivel_acesso == 'COORDENADOR'` e o objeto acessado pertence à `Profile.escola` do usuário (ou é Diretor, que sempre passa).
  - `MonitorRequiredMixin` — passa para Diretor, para o Coordenador da unidade da oficina e para o Monitor **designado naquela oficina** (`oficina.monitores` contém o usuário). Usado só nas views de frequência/lista de alunos matriculados; **nunca** nas views de cadastro/edição de aluno, oficina ou usuário.
- O escopo é sempre aplicado no **queryset** (ex.: Monitor lista `Oficina.objects.filter(monitores=request.user)`), não só no template.
- Implementar os 3 níveis como **Django Groups** (`Diretor`, `Coordenador`, `Monitor`) para bundles de `Permission` padrão do Django, combinados com `Profile.escola`/`nivel_acesso` para o escopo por unidade — é o padrão exato usado na origem (grupo `Coordenador` + `Profile.escola`).

## 4. Modelo de dados a replicar

### `EscolaNaica`
Já descrita acima.

### `TipoOficina`
- `escola` (FK), `nome`, `cor` (opcional, só estético pra UI)
- `unique_together = ('escola', 'nome')`

### `Oficina` (era `Curso`)
- `escola` (FK), `tipo_oficina` (FK), `nome`, `carga_horaria`, `vagas`
- `data_inicio`, `data_fim`, `turno` (Manhã/Tarde/Noite), `horario`, `horario_fim`
- `status` (`Aberta` / `Em Andamento` / `Concluído` / `Arquivado`)
- `nome_monitor`/`telefone_monitor` (quem conduz a oficina — pode ou não ser o usuário logado como Monitor)
- `monitores` (M2M `User`, só usuários com `nivel_acesso='MONITOR'`, de qualquer unidade) — define em quais oficinas cada Monitor lança frequência (ver seção 2.2)

### Cadastro do Aluno — formulário em 6 etapas

Baseado no formulário físico da Prodaub, dividido em etapas pra não ficar uma tela só gigante. Cada etapa vira (ou alimenta) um model próprio:

**Etapa 1 — Dados do Aluno** (`Aluno`)
Identificação: CPF\*, Nome completo\*, Nome da mãe\*, Data de nascimento\*, Sexo\*, Naturalidade\*, NIS
Escolaridade: Nome da escola\*, Ano escolar\*
(endereço vai pra `Endereco`, etapa separada abaixo)

**`Endereco`** (OneToOne com `Aluno`)
CEP\* (com busca automática via ViaCEP, mas mantendo edição manual), Logradouro, Número, Bairro, Complemento, Cidade, Estado — tornar logradouro/bairro/cidade **obrigatórios** (no formulário original da Prodaub eles não eram, e isso gerava endereço incompleto)

**Etapa 2 — Responsável** (`Responsavel`, entidade própria e reaproveitável — ver abaixo)
Identificação: CPF\*, Nome completo\*, Grau de parentesco\*, Data de nascimento\*
Contato: Celular\*, E-mail
Documento: Número do documento, Data de expedição\*, Órgão expedidor\*, UF\*
Situação de trabalho e renda: Trabalha?\* (condicional → libera Carteira assinada?, que por sua vez libera Nº/Série CTPS), Contribui com a Previdência?, Recebe algum benefício?\* (condicional → libera Qual benefício)

**`AlunoResponsavel`** (tabela intermediária: `aluno` FK, `responsavel` FK, `grau_parentesco`) — permite um `Responsavel` estar ligado a mais de um `Aluno` (irmãos), e reaproveitar o cadastro por CPF: ao digitar o CPF do responsável na etapa 2, se ele já existir no sistema, pré-preencher os dados automaticamente.

**Etapa 3 — Família e Emergência**
- `MembroFamiliar` (FK `aluno`): nome, parentesco, data de nascimento, ocupação, renda mensal — lista dinâmica ("Adicionar membro") com botão "Calcular renda familiar" (soma simples, sem score/priorização — isso não entra no Naicas).
- `ContatoEmergencia` (FK `aluno`, mínimo 2 registros): Nome\*, Parentesco\*, Celular\*

**Etapa 4 — Saúde** → `FichaSaude` (**OneToOne com `Aluno`**)
Assistência médica: Tipo (SUS / plano / ambos), Qual(is)
Condições: Possui algum problema de saúde?\* (condicional → libera campo "Especifique")
Medicação: Usa medicação controlada?\* (condicional → libera Qual medicação, Há quanto tempo, Reações provocadas) — **separar isso em Sim/Não + campo de detalhe**, no formulário original da Prodaub é um texto livre só, o que dificulta buscar/filtrar depois
Alergias: Especifique
**Dado sensível (LGPD)**: restringir a visualização desta etapa por nível de acesso — Monitor, por exemplo, deveria ver só alergias/medicação (o mínimo pra agir numa emergência), nunca o restante do prontuário. Implementar como permissão separada checada na view, não só escondida no template.

**Etapa 5 — Anexos** → `TipoDocumento` (tabela de referência) + `Anexo`
`TipoDocumento`: `nome`, `obrigatorio` (bool) — fica no Django Admin, assim dá pra adicionar/exigir novos tipos de documento sem mexer em código. Tipos sugeridos pra já cadastrar: certidão de nascimento ou RG do aluno, CPF do aluno, documento com foto do responsável, comprovante de endereço, declaração de matrícula escolar, cartão SUS, comprovante de NIS/CadÚnico, laudo médico (se houver), foto 3x4, termo de autorização de uso de imagem assinado.
`Anexo`: `aluno` (FK), `tipo_documento` (FK), `arquivo`, `data_envio` (auto_now_add), `enviado_por` (FK User) — a tela de anexos mostra o que já foi enviado e o que ainda falta, cruzando com `TipoDocumento.obrigatorio`.

**Etapa 6 — Matrícula e Revisão** → `Matricula`
`aluno` (FK), `escola` (FK — unidade de atendimento\*), `oficina` (FK — turma/oficina\*), `turno`\*, `data_inscricao` (auto_now_add), `status` (`cursando` / `concluido` / `desistente`), `data_conclusao`, `data_desistencia`
A matrícula fica como última etapa de propósito: no modelo, o aluno pode existir cadastrado (etapas 1-5 completas) **antes** de ser efetivamente matriculado numa oficina — útil pra fila de interesse/espera.
A **ação de matricular** é restrita a Diretor e Coordenador de Unidade — Monitor não matricula, só lança frequência.

### Ficha de Frequência
- `RegistroAula`: `oficina` (FK), `data_aula`, `observacoes`, `lancado_por` (FK `User`, quem lançou a chamada, que guarda o histórico da escala); `unique_together = ('oficina', 'data_aula')` (uma aula por dia por oficina)
- `Chamada`: `registro_aula` (FK), `matricula` (FK), `status_presenca` (P/F/J — Presente/Falta/Justificado), `observacoes`; `unique_together = ('registro_aula', 'matricula')`
- Tela de lançamento de chamada acessível por Diretor, Coordenador de Unidade e **Monitor** (este é o caso de uso principal do papel Monitor). Coordenador fica escopado à própria unidade, e o Monitor só às oficinas em que está designado, em qualquer unidade.

### Resumo do bloco de models do cadastro
```
Aluno               → identificação + escolaridade
Endereco            → OneToOne com Aluno
Responsavel         → entidade própria (reaproveitável por CPF)
AlunoResponsavel    → tabela intermediária (grau de parentesco)
MembroFamiliar      → FK Aluno (nome, parentesco, nascimento, ocupação, renda)
ContatoEmergencia   → FK Aluno
FichaSaude          → OneToOne com Aluno (acesso restrito — LGPD)
TipoDocumento        → tabela de tipos de anexo (nome, obrigatório?)
Anexo                → FK Aluno, FK TipoDocumento, arquivo, data_envio, enviado_por
Matricula             → FK Aluno, escola, oficina, turno, data_inscricao, status
```

## 5. Infraestrutura e deploy (replicar tal qual, simplificado sem Redis/Channels)

- `docker-compose.yml`: serviços `db` (postgres:16-alpine, porta só em `127.0.0.1`) e `web` (build local, bind-mount `.:/app`, variáveis de ambiente via `.env`)
- `entrypoint.sh`: roda `migrate --noinput` + `collectstatic --noinput` (com `set -e` pra falhar o boot se a migração falhar, em vez de subir quebrado) e então inicia o Gunicorn
- `atualizar.sh` (rodado na VPS): pergunta se quer backup → `git fetch && git reset --hard origin/main && git clean -fd` → `docker compose up -d --build` → loop de healthcheck (`curl -H "Host: <seu-dominio>" http://localhost:8000/` por até 60s, **com o header Host correto** — sem isso o Django rejeita por `ALLOWED_HOSTS` e o script reporta falso-negativo) → `docker image prune -f`

## 6. Checklist de adaptação para o Naicas

- [x] Campos do formulário de inscrição/cadastro do aluno definidos (seção 4 — formulário em 6 etapas)
- [x] Nomes dos 3 níveis de acesso e dos Groups: **Diretor / Coordenador / Monitor**
- [x] Divisão em apps Django definida (seção 2.1)
- [x] Infra base criada: Docker Compose, settings via `.env`, `entrypoint.sh`, `atualizar.sh`
- [x] **Etapa 1 — Fundação:** `EscolaNaica`, `Profile` + Groups, login/logout, middleware, mixins, CRUD de unidades e usuários (Diretor)
- [ ] Etapa 2 — Oficinas (`TipoOficina`, `Oficina`, designação de Monitores)
- [ ] Etapa 3 — Cadastro do aluno (3a dados/endereço/responsável, 3b família/emergência, 3c saúde)
- [ ] Etapa 4 — Anexos
- [ ] Etapa 5 — Matrícula
- [ ] Etapa 6 — Frequência
- [ ] *(pós-MVP)* Definir o domínio/VPS de destino (`ALLOWED_HOSTS` e o `HEALTHCHECK_HOST` do `atualizar.sh`)
- [ ] *(pós-MVP)* Decidir a regra de visualização de `FichaSaude` por nível de acesso (sugestão: Monitor vê só alergias/medicação)
- [ ] *(pós-MVP)* Integrar ao SSO Keycloak `desenvolvimento-social`
