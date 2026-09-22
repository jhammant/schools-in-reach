#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PHP_BIN="${PHP_BIN:-php}"
if ! command -v "$PHP_BIN" >/dev/null 2>&1; then
    PHP_BIN=/opt/homebrew/bin/php
fi
while IFS= read -r -d '' file; do
    "$PHP_BIN" -l "$file"
done < <(find "$ROOT/integrations/wordpress" -type f -name '*.php' -print0)
"$PHP_BIN" "$ROOT/integrations/wordpress/tests/run.php"
mkdir -p "$ROOT/site/downloads"
# Build a fresh archive so removed files cannot linger in an existing ZIP.
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
cd "$ROOT/integrations/wordpress"
zip -X -q -r "$TEMP_DIR/schools-in-reach-wordpress.zip" schools-in-reach -x '*/.DS_Store' '*/.*'
unzip -tq "$TEMP_DIR/schools-in-reach-wordpress.zip"
mv "$TEMP_DIR/schools-in-reach-wordpress.zip" "$ROOT/site/downloads/schools-in-reach-wordpress.zip"
printf 'Built %s\n' "$ROOT/site/downloads/schools-in-reach-wordpress.zip"
