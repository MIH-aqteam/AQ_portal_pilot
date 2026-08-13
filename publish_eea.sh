#!/bin/bash

set -Eeuo pipefail

echo "=================================================="
echo "       AQ PORTAL - PUBLISH TO EEA GITHUB"
echo "=================================================="
echo

echo "Building local documentation..."
echo

rm -rf build/html

python3 -m sphinx \
    --keep-going \
    -E \
    -a \
    -b html \
    docs \
    build/html

echo
echo "✓ Local build completed successfully."
echo

CURRENT_BRANCH=$(git branch --show-current)

if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "Publication cancelled: current branch is '$CURRENT_BRANCH'."
    echo "Merge your changes into main before publishing."
    exit 1
fi

if ! git remote get-url eea >/dev/null 2>&1; then
    echo "Publication cancelled: remote 'eea' is not configured."
    exit 1
fi

git status --short

echo
echo "--------------------------------------------------"
read -r -p "Commit message: " COMMITMSG

if [ -z "$COMMITMSG" ]; then
    echo
    echo "❌ No commit message entered. Publication cancelled."
    exit 1
fi

echo
echo "Staging files..."
git add -A

echo
echo "Files staged for publication:"
git diff --cached --stat

if git diff --cached --quiet; then
    echo
    echo "Nothing to commit."
else
    echo
    echo "Creating commit..."
    git commit -m "$COMMITMSG"
fi

echo
echo "Pushing to EEA GitHub..."
git push eea main

echo
echo "=================================================="
echo "✓ Publication completed successfully."
echo
echo "Repository : https://github.com/eeadata/AQ.Portal"
echo "Website    : to be confirmed after GitHub Pages deployment"
echo
echo "GitHub Actions is now deploying the updated website."
echo "=================================================="
