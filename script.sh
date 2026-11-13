#!/usr/bin/env bash
# Atualiza o checkout da VPS a partir de origin/main, preservando dados locais.
set -Eeuo pipefail

main() {
ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

AUTO_UPDATE=0
case "${1:-}" in
    '') ;;
    --auto) AUTO_UPDATE=1 ;;
    *) printf 'Uso: bash script.sh [--auto]\n' >&2; exit 2 ;;
esac

BRANCH="${DEPLOY_BRANCH:-main}"
KEEP_BACKUPS="${KEEP_BACKUPS:-10}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
DB_CONTAINER="${DB_CONTAINER:-naicas-db}"
WEB_PORT="${WEB_PORT:-}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-}"
STAMP="$(date +%Y%m%d_%H%M%S)_$$"
BACKUP_CONTAINER_FILE=""

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fail() { log "ERRO: $*" >&2; exit 1; }

env_value() {
    local key="$1" value=""
    if [[ -f .env ]]; then
        value="$(grep -m1 "^${key}=" .env 2>/dev/null | cut -d= -f2- || true)"
    fi
    value="${value%$'\r'}"
    value="${value#\"}"; value="${value%\"}"
    value="${value#\'}"; value="${value%\'}"
    printf '%s' "$value"
}

WEB_PORT="${WEB_PORT:-$(env_value WEB_PORT)}"
WEB_PORT="${WEB_PORT:-8020}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-$(env_value HEALTHCHECK_HOST)}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-localhost}"

for command in git docker curl flock; do
    command -v "$command" >/dev/null 2>&1 || fail "Comando obrigatório não encontrado: $command"
done
[[ "$KEEP_BACKUPS" =~ ^[1-9][0-9]*$ ]] || fail 'KEEP_BACKUPS deve ser um inteiro maior que zero.'

exec 9>"$ROOT_DIR/.deploy.lock"
if ! flock -n 9; then
    [[ "$AUTO_UPDATE" -eq 1 ]] && exit 0
    fail 'Já existe outra atualização em andamento.'
fi

CURRENT_BRANCH="$(git branch --show-current)"
[[ "$CURRENT_BRANCH" == "$BRANCH" ]] || fail "O checkout está na branch '$CURRENT_BRANCH'; esperado: '$BRANCH'."
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || \
    fail 'Há alterações locais em arquivos rastreados. Faça commit ou descarte-as antes do deploy.'

log "Buscando origin/$BRANCH..."
GIT_TERMINAL_PROMPT=0 git fetch --prune origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
OLD_REV="$(git rev-parse HEAD)"
REMOTE_REV="$(git rev-parse "origin/$BRANCH")"
DEPLOY_STATE="$(git rev-parse --git-path naicas-last-deploy)"

if ! git merge-base --is-ancestor "$OLD_REV" "$REMOTE_REV"; then
    fail "A branch local divergiu de origin/$BRANCH. Nenhum reset foi feito."
fi

# O timer consulta o Git sem reconstruir/reiniciar um deploy já concluído.
# Se a execução anterior falhou após o merge, tenta novamente a mesma revisão.
if [[ "$AUTO_UPDATE" -eq 1 && "$OLD_REV" == "$REMOTE_REV" && -f "$DEPLOY_STATE" ]] && \
    [[ "$(cat "$DEPLOY_STATE")" == "$OLD_REV" ]]; then
    log 'Nenhuma atualização pendente.'
    exit 0
fi

if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
    DOCKER_USE_SUDO=0
else
    [[ "$AUTO_UPDATE" -eq 0 ]] || fail 'O serviço automático precisa de acesso ao socket do Docker. Execute instalar_auto_update.sh.'
    command -v sudo >/dev/null 2>&1 || fail 'Docker não está acessível e sudo não está disponível.'
    log 'Solicitando acesso ao Docker via sudo.'
    sudo -v
    DOCKER=(sudo docker)
    DOCKER_USE_SUDO=1
fi

compose() { "${DOCKER[@]}" compose "$@"; }
cleanup_container_dump() {
    if [[ -n "$BACKUP_CONTAINER_FILE" ]]; then
        "${DOCKER[@]}" exec "$DB_CONTAINER" rm -f "$BACKUP_CONTAINER_FILE" >/dev/null 2>&1 || true
    fi
}
trap cleanup_container_dump EXIT

if [[ "$OLD_REV" != "$REMOTE_REV" ]]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/pre_update_${STAMP}.dump"
    BACKUP_CONTAINER_FILE="/tmp/pre_update_${STAMP}.dump"

    log "Criando backup do PostgreSQL em $BACKUP_FILE..."
    "${DOCKER[@]}" exec "$DB_CONTAINER" sh -c \
        'umask 077; pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$1" && test -s "$1" && pg_restore --list "$1" >/dev/null' \
        sh "$BACKUP_CONTAINER_FILE"
    "${DOCKER[@]}" cp "$DB_CONTAINER:$BACKUP_CONTAINER_FILE" "$BACKUP_FILE"
    if [[ "$DOCKER_USE_SUDO" -eq 1 ]]; then
        sudo chown "$(id -u):$(id -g)" "$BACKUP_FILE"
    fi
    chmod 600 "$BACKUP_FILE"
    [[ -s "$BACKUP_FILE" ]] || fail 'O backup do banco ficou vazio.'
    cleanup_container_dump
    BACKUP_CONTAINER_FILE=""

    log "Avançando a branch local até $REMOTE_REV..."
    git merge --ff-only "origin/$BRANCH"
else
    log 'O checkout já está na revisão mais recente do Git.'
fi

log 'Validando a configuração do Compose...'
compose config --quiet

log 'Construindo e iniciando os serviços deste Compose...'
compose up -d --build

log 'Aguardando a aplicação responder...'
READY=0
for attempt in $(seq 1 30); do
    if curl -fsS --max-time 5 -o /dev/null \
        -H "Host: $HEALTHCHECK_HOST" "http://127.0.0.1:${WEB_PORT}/"; then
        READY=1
        break
    fi
    sleep 2
done

if [[ "$READY" -ne 1 ]]; then
    fail 'A aplicação não respondeu após 30 tentativas. Consulte os logs do contêiner naicas-app. O backup pré-atualização foi preservado.'
fi

if [[ -d "$BACKUP_DIR" ]]; then
    # Os nomes começam pelo timestamp, então o glob já traz a ordem cronológica.
    # Não depende de find -printf (indisponível no BusyBox do ZimaOS).
    BACKUPS=()
    for backup in "$BACKUP_DIR"/pre_update_*.dump; do
        [[ ! -f "$backup" ]] || BACKUPS+=("$backup")
    done
    EXCESS_BACKUPS=$(( ${#BACKUPS[@]} - KEEP_BACKUPS ))
    if [[ "$EXCESS_BACKUPS" -gt 0 ]]; then
        for old_backup in "${BACKUPS[@]:0:$EXCESS_BACKUPS}"; do
            rm -f -- "$old_backup"
        done
    fi
fi

printf '%s\n' "$(git rev-parse HEAD)" > "${DEPLOY_STATE}.tmp"
mv -f -- "${DEPLOY_STATE}.tmp" "$DEPLOY_STATE"
log "Deploy concluído na revisão $(git rev-parse --short HEAD)."
}

# Carregar a função inteira evita ler trechos diferentes deste arquivo enquanto
# o próprio checkout é atualizado pelo git merge.
main "$@"
