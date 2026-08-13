#!/bin/bash

set -Eeuo pipefail

# Go to the project directory
cd "$(dirname "$0")"

echo "Building local documentation..."

# Remove previous local build
rm -rf build/html

# Build the documentation
python3 -m sphinx \
    --keep-going \
    -E \
    -a \
    -b html \
    docs \
    build/html

echo "Build completed successfully!"

if command -v open >/dev/null 2>&1; then
    open build/html/index.html
fi

echo "Done!"
