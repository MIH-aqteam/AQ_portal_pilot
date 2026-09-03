#!/bin/bash

set -Eeuo pipefail

# Always run from the AQ Portal project root.
cd "$(dirname "$0")"

if ! /usr/bin/python3 --version >/dev/null 2>&1; then
    echo "❌ Python 3 was not found. News creation cancelled."
    exit 1
fi

exec /usr/bin/python3 scripts/new_news.py "$@"