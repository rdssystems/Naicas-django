#!/usr/bin/env bash
# Instala na VPS a consulta de origin/main e o deploy a cada minuto.
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_USER="$(id -un)"
BASH_BIN="$(command -v bash)"

[[ "$(id -u)" -ne 0 ]] || {
    printf 'Execute como o dono do checkout, sem sudo: bash instalar_auto_update.sh\n' >&2
    exit 1
}
for command in sudo systemctl systemd-analyze docker stat getent install; do
    command -v "$command" >/dev/null || { printf 'Comando obrigatório ausente: %s\n' "$command" >&2; exit 1; }
done
[[ -S /var/run/docker.sock ]] || { printf 'Socket /var/run/docker.sock não encontrado.\n' >&2; exit 1; }
[[ "$ROOT_DIR" != *'%'* && "$ROOT_DIR" != *'"'* && "$ROOT_DIR" != *'\'* && "$ROOT_DIR" != *$'\n'* ]] || {
    printf 'O caminho do checkout contém caracteres incompatíveis com a unidade systemd.\n' >&2
    exit 1
}

DOCKER_GID="$(command stat -c '%g' /var/run/docker.sock)"
[[ "$DOCKER_GID" -ne 0 ]] || { printf 'O socket Docker precisa de um grupo dedicado, como docker.\n' >&2; exit 1; }
getent group "$DOCKER_GID" >/dev/null
bash -n "$ROOT_DIR/script.sh"
sudo -v

UNIT_DIR="$(mktemp -d)"
trap 'rm -rf -- "$UNIT_DIR"' EXIT
cat > "$UNIT_DIR/naicas-update.service" <<EOF
[Unit]
Description=Atualizar Naicas a partir de origin/main
Wants=network-online.target
After=network-online.target docker.service
Requires=docker.service

[Service]
Type=oneshot
User=$DEPLOY_USER
SupplementaryGroups=$DOCKER_GID
WorkingDirectory="$ROOT_DIR"
ExecStart=$BASH_BIN "$ROOT_DIR/script.sh" --auto
Environment=GIT_TERMINAL_PROMPT=0
UMask=0077
NoNewPrivileges=true
TimeoutStartSec=30min
EOF

cat > "$UNIT_DIR/naicas-update.timer" <<'EOF'
[Unit]
Description=Consultar atualizações do Naicas a cada minuto

[Timer]
OnActiveSec=15s
OnUnitInactiveSec=1min
AccuracySec=5s
Unit=naicas-update.service

[Install]
WantedBy=timers.target
EOF

sudo systemd-analyze verify "$UNIT_DIR/naicas-update.service" "$UNIT_DIR/naicas-update.timer"
sudo install -m 644 "$UNIT_DIR/naicas-update.service" /etc/systemd/system/naicas-update.service
sudo install -m 644 "$UNIT_DIR/naicas-update.timer" /etc/systemd/system/naicas-update.timer
sudo systemctl daemon-reload
sudo systemctl enable --now naicas-update.timer
sudo systemctl start --no-block naicas-update.service

printf '\nAtualização automática instalada para %s em %s.\n' "$DEPLOY_USER" "$ROOT_DIR"
printf 'Acompanhar: sudo journalctl -u naicas-update.service -n 50 --no-pager\n'
printf 'Parar: sudo systemctl disable --now naicas-update.timer\n'
