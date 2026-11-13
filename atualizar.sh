#!/usr/bin/env bash
# Compatibilidade com o comando antigo: o deploy único fica em script.sh.
exec bash "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/script.sh" "$@"
