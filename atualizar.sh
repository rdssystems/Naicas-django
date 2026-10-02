#!/bin/bash
# Atualiza o Naicas na VPS: backup opcional -> git pull -> rebuild -> healthcheck.

cd "$(dirname "$0")"

echo "--- Iniciando atualização do Naicas ---"

# Lê WEB_PORT, HEALTHCHECK_HOST, DB_USER e DB_NAME do .env
set -a
[ -f .env ] && . ./.env
set +a
WEB_PORT="${WEB_PORT:-8020}"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-localhost}"

# ──────────────────────────────────────────────────
# 0. Backup pré-atualização (opcional)
# ──────────────────────────────────────────────────
read -p ">>> Deseja fazer backup antes de atualizar? (s/N): " FAZER_BACKUP

if [[ "$FAZER_BACKUP" =~ ^[sS]$ ]]; then
    mkdir -p backups
    BACKUP_FILE="backups/pre_update_$(date +%Y%m%d_%H%M%S).dump"
    echo ">>> Gerando backup do banco em $BACKUP_FILE..."
    if sudo docker exec naicas-db pg_dump -U "${DB_USER:-naicas_user}" -Fc "${DB_NAME:-naicas_db}" > "$BACKUP_FILE"; then
        echo ">>> Backup salvo."
    else
        echo "!!! Falha no backup. Abortando a atualização."
        rm -f "$BACKUP_FILE"
        exit 1
    fi
    # Mantém só os 10 mais recentes
    ls -1t backups/pre_update_*.dump 2>/dev/null | tail -n +11 | xargs -r rm -f
else
    echo ">>> Backup pulado."
fi

# ──────────────────────────────────────────────────
# 1. Git pull
# ──────────────────────────────────────────────────
echo ">>> Puxando mudanças do Git..."
git fetch origin main
git reset --hard origin/main
# -e backups/: não apagar os dumps (estão no .gitignore, então o clean -fd os pouparia
# de qualquer forma; explícito para não depender disso)
git clean -fd -e backups/

# ──────────────────────────────────────────────────
# 2. Rebuild dos containers
# ──────────────────────────────────────────────────
echo ">>> Reconstruindo containers..."
sudo docker compose up -d --build

# ──────────────────────────────────────────────────
# 3. Healthcheck
# ──────────────────────────────────────────────────
# O entrypoint.sh já roda migrate + collectstatic antes de subir o Gunicorn
# (e aborta com set -e se o migrate falhar). Aqui só esperamos a aplicação
# responder. O header Host é obrigatório: sem ele o Django rejeita com 400
# DisallowedHost e o healthcheck dá falso-negativo.
echo ">>> Aguardando a aplicação ficar pronta..."
PRONTO=0
for i in $(seq 1 30); do
    if curl -sf -o /dev/null -H "Host: ${HEALTHCHECK_HOST}" "http://localhost:${WEB_PORT}/"; then
        PRONTO=1
        break
    fi
    sleep 2
done

if [ "$PRONTO" -eq 1 ]; then
    echo ">>> Aplicação respondendo normalmente."
else
    echo "!!! ATENÇÃO: a aplicação não respondeu após 60s. Verifique 'sudo docker logs naicas-app --tail 100' antes de considerar o deploy concluído."
fi

# ──────────────────────────────────────────────────
# 4. Limpeza
# ──────────────────────────────────────────────────
echo ">>> Limpando imagens antigas..."
sudo docker image prune -f

echo "--- Atualização concluída! ---"
