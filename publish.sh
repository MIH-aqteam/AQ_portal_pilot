#!/bin/bash

set -e

clear

echo "=================================================="
echo "        AQ PORTAL - PUBLISH TO GITHUB"
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

echo "Creating commit..."
git commit -m "$COMMITMSG"

echo
echo "Pushing to personal GitHub..."
git push personal main

echo
echo "=================================================="
echo "✓ Publication completed successfully."
echo
echo "Repository : https://github.com/MIH-aqteam/AQ_portal_pilot"
echo "Website    : https://mih-aqteam.github.io/AQ_portal_pilot/"
echo
echo "GitHub Actions is now deploying the updated website."
echo "=================================================="
