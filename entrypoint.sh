#!/bin/sh
# set -e: se o migrate falhar, o container morre aqui em vez de subir o
# servidor com o schema desatualizado/quebrado silenciosamente.
set -e

# Espera o Postgres aceitar conexões (o depends_on sozinho não garante isso).
until pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-naicas_user}" -q; do
    echo "Aguardando o banco de dados..."
    sleep 1
done

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "$DEBUG" = "True" ]; then
    echo "Iniciando em DESENVOLVIMENTO (runserver com auto reload)..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Iniciando em PRODUÇÃO (Gunicorn)..."
    exec gunicorn naicas.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-3}" \
        --timeout "${GUNICORN_TIMEOUT:-60}" \
        --access-logfile - \
        --error-logfile -
fi
