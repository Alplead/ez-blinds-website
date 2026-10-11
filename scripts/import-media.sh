#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <file-or-directory> [more files/directories...]"
  exit 1
fi

COMPOSE="docker compose -f .devcontainer/docker-compose.yml"

for src in "$@"; do
  if [ -d "$src" ]; then
    find "$src" -maxdepth 1 -type f \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.webp' \) -print0 |
      while IFS= read -r -d '' file; do
        base="$(basename "$file")"
        $COMPOSE cp "$file" wordpress:"/tmp/$base"
        $COMPOSE exec -T wordpress php /tmp/wp-cli.phar media import "/tmp/$base" --allow-root --porcelain
      done
  else
    base="$(basename "$src")"
    $COMPOSE cp "$src" wordpress:"/tmp/$base"
    $COMPOSE exec -T wordpress php /tmp/wp-cli.phar media import "/tmp/$base" --allow-root --porcelain
  fi
done
