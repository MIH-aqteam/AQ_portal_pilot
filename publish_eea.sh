#!/bin/bash

set -e

clear

echo "=================================================="
echo "       AQ PORTAL - PUBLISH TO EEA GITHUB"
echo "=================================================="
echo

echo "Building local documentation..."
echo

rm -rf build/html

python3 -m sphinx \
    -W \
    --keep-going \
    -E \
    -a \
    -b html \
    docs \
    build/html

echo
echo "✓ Local build completed successfully (no warnings)."
echo

git status --short

echo
echo "--------------------------------------------------"
read -p "Commit message: " COMMITMSG

if [ -z "$COMMITMSG" ]; then
    echo
    echo "❌ No commit message entered. Publication cancelled."
    exit 1
fi

echo
echo "Staging files..."
git add -A

if git diff --cached --quiet; then
    echo
    echo "Nothing to commit."
else
    echo "Creating commit..."
    git commit -m "$COMMITMSG"
fi

echo
echo "Pushing to EEA GitHub..."
git push eea main

echo
echo "=================================================="
echo "✓ Publication to EEA GitHub completed successfully."
echo
echo "Repository : https://github.com/eeadata/AQ.Portal"
echo "Website    : to be confirmed after GitHub Pages deployment"
echo
echo "GitHub Actions is now deploying the updated website."
echo "=================================================="
