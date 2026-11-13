#!/usr/bin/env bash
# Exercita o fluxo de deploy em repositórios temporários, sem contêineres reais.
set -Eeuo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$(mktemp -d)"
trap 'rm -rf -- "$FIXTURE"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
export DOCKER_LOG="$FIXTURE/docker.log"
mkdir -p "$FIXTURE/bin"

cat > "$FIXTURE/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$DOCKER_LOG"
if [[ "$1" == cp ]]; then printf 'backup simulado\n' > "$3"; fi
if [[ "$1 $2" == 'compose up' && "${FAKE_COMPOSE_FAIL:-0}" == 1 ]]; then exit 1; fi
EOF
printf '#!/usr/bin/env bash\nprintf "%%s" "${FAKE_HTTP_STATUS:-200}"\n' > "$FIXTURE/bin/curl"
printf '#!/usr/bin/env bash\nexit 0\n' > "$FIXTURE/bin/sleep"
chmod +x "$FIXTURE/bin/"*
export PATH="$FIXTURE/bin:$PATH"

git init --bare -q "$FIXTURE/origin.git"
git init -q -b main "$FIXTURE/dev"
git -C "$FIXTURE/dev" config user.name 'Deploy fixture'
git -C "$FIXTURE/dev" config user.email 'deploy@example.invalid'
cp "$SOURCE_DIR/script.sh" "$FIXTURE/dev/script.sh"
printf '.deploy.lock\nbackups/\n' > "$FIXTURE/dev/.gitignore"
git -C "$FIXTURE/dev" add .
git -C "$FIXTURE/dev" commit -qm initial
git -C "$FIXTURE/dev" remote add origin "$FIXTURE/origin.git"
git -C "$FIXTURE/dev" push -q -u origin main
git clone -q --branch main "$FIXTURE/origin.git" "$FIXTURE/vps"
cd "$FIXTURE/vps"

run_auto() { bash ./script.sh --auto > "$FIXTURE/run.log" 2>&1; }
expect_failure() {
    if run_auto; then printf 'ERRO: era esperada uma falha.\n' >&2; exit 1; fi
}
publish() {
    printf '%s\n' "$1" > "$FIXTURE/dev/release.txt"
    git -C "$FIXTURE/dev" add .
    git -C "$FIXTURE/dev" commit -qm "$1"
    git -C "$FIXTURE/dev" push -q origin main
}

run_auto
[[ "$(cat .git/naicas-last-deploy)" == "$(git rev-parse HEAD)" ]]
grep -q '^compose up' "$DOCKER_LOG"
printf 'PASS: primeiro deploy grava a revisão concluída.\n'

: > "$DOCKER_LOG"
run_auto
[[ ! -s "$DOCKER_LOG" ]]
printf 'PASS: revisão inalterada não acessa o Docker nem reinicia serviços.\n'

# Alterar o próprio script também verifica a segurança durante o self-update.
sed -i '2i# Script atualizado pela fixture.' "$FIXTURE/dev/script.sh"
publish release-1
run_auto
[[ "$(git rev-parse HEAD)" == "$(git -C "$FIXTURE/dev" rev-parse HEAD)" ]]
[[ "$(cat .git/naicas-last-deploy)" == "$(git rev-parse HEAD)" ]]
[[ -s "$(find backups -name '*.dump' -print -quit)" ]]
[[ "$(stat -c '%a' "$(find backups -name '*.dump' -print -quit)")" == 600 ]]
grep -q 'pg_restore --list' "$DOCKER_LOG"
printf 'PASS: atualização faz backup restrito e avança o Git por fast-forward.\n'

PREVIOUS_SUCCESS="$(cat .git/naicas-last-deploy)"
publish release-2
export FAKE_COMPOSE_FAIL=1
expect_failure
[[ "$(cat .git/naicas-last-deploy)" == "$PREVIOUS_SUCCESS" ]]
unset FAKE_COMPOSE_FAIL
: > "$DOCKER_LOG"
run_auto
grep -q '^compose up' "$DOCKER_LOG"
[[ "$(cat .git/naicas-last-deploy)" == "$(git rev-parse HEAD)" ]]
printf 'PASS: falha no build não marca sucesso; a próxima consulta tenta novamente.\n'

PREVIOUS_SUCCESS="$(cat .git/naicas-last-deploy)"
publish release-healthcheck
export FAKE_HTTP_STATUS=301
expect_failure
[[ "$(cat .git/naicas-last-deploy)" == "$PREVIOUS_SUCCESS" ]]
unset FAKE_HTTP_STATUS
run_auto
[[ "$(cat .git/naicas-last-deploy)" == "$(git rev-parse HEAD)" ]]
printf 'PASS: redirecionamento HTTPS não conta como aplicação pronta; exige HTTP 200 no login.\n'

: > "$DOCKER_LOG"
(
    exec 8>.deploy.lock
    flock -n 8
    run_auto
)
[[ ! -s "$DOCKER_LOG" ]]
printf 'PASS: consulta simultânea respeita o lock e sai sem erro.\n'

for index in {01..12}; do printf 'antigo\n' > "backups/pre_update_20000101_0000${index}.dump"; done
KEEP_BACKUPS=3 bash ./script.sh > "$FIXTURE/run.log" 2>&1
REMAINING_BACKUPS=(backups/pre_update_*.dump)
[[ "${#REMAINING_BACKUPS[@]}" -eq 3 ]]
[[ "${REMAINING_BACKUPS[-1]}" != *20000101* ]]
printf 'PASS: retenção remove cópias antigas sem depender de find -printf.\n'

: > "$DOCKER_LOG"
printf 'edição local\n' >> release.txt
expect_failure
[[ ! -s "$DOCKER_LOG" ]]
git restore release.txt
printf 'PASS: arquivo rastreado alterado impede deploy.\n'

git config user.name 'Deploy fixture'
git config user.email 'deploy@example.invalid'
printf 'commit local\n' >> release.txt
git add release.txt
git commit -qm divergent
expect_failure
[[ ! -s "$DOCKER_LOG" ]]
printf 'PASS: branch divergente é preservada sem reset.\n'
