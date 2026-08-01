#!/bin/bash

set -e

# Go to the project directory
cd "$(dirname "$0")"

echo "====================================="
echo "Building local AQ Portal..."
echo "====================================="

# Remove previous local build
rm -rf build

# Build the documentation
python3 -m sphinx -E -a -b html docs build/html

echo ""
echo "====================================="
echo "Build completed successfully!"
echo "====================================="
echo "Open: build/html/index.html"

open build/html/index.html
# open build/html/index.html
