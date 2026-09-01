#!/bin/bash

set -Eeuo pipefail

EXPECTED_BRANCH="main"
EXPECTED_REMOTE="personal"
EXPECTED_REPO="MIH-aqteam/AQ_portal_pilot"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build/html"

cd "$SCRIPT_DIR"
clear 2>/dev/null || true

fail() {
    echo
    echo "ERROR: $1"
    echo "Publication cancelled."
    exit 1
}

confirm() {
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "$answer" == "y" || "$answer" == "Y" ]]
}

echo "============================================================"
echo "          AQ PORTAL - PERSONAL PILOT PUBLICATION"
echo "============================================================"
echo
echo "Destination:"
echo "  Personal GitHub repository"
echo "  $EXPECTED_REPO"
echo
echo "This script will:"
echo "  1. Verify the project, branch and personal remote"
echo "  2. Show the current Git status"
echo "  3. Build the Sphinx website with warnings as errors"
echo "  4. Show and stage all resulting source changes"
echo "  5. Create one Git commit"
echo "  6. Push main to the personal pilot repository"
echo
echo "No commit or push occurs without a separate confirmation."
echo "Nothing has been changed yet."
echo
read -r -p "Press ENTER to begin verification, or Ctrl-C to abort."

echo
echo "------------------------------------------------------------"
echo "1. VERIFYING PROJECT AND DESTINATION"
echo "------------------------------------------------------------"
echo

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
    fail "This directory is not a Git repository."

[[ -f "$SCRIPT_DIR/docs/conf.py" ]] || \
    fail "docs/conf.py was not found. Run this script from the AQ Portal project copy."

CURRENT_BRANCH="$(git branch --show-current)"
echo "Project        : $SCRIPT_DIR"
echo "Current branch : $CURRENT_BRANCH"

[[ "$CURRENT_BRANCH" == "$EXPECTED_BRANCH" ]] || \
    fail "Publication must be performed from branch '$EXPECTED_BRANCH', not '$CURRENT_BRANCH'."

git remote get-url "$EXPECTED_REMOTE" >/dev/null 2>&1 || \
    fail "Git remote '$EXPECTED_REMOTE' does not exist."

REMOTE_URL="$(git remote get-url "$EXPECTED_REMOTE")"
echo "Remote         : $EXPECTED_REMOTE"
echo "Remote URL     : $REMOTE_URL"

case "$REMOTE_URL" in
    "https://github.com/$EXPECTED_REPO"|\
    "https://github.com/$EXPECTED_REPO.git"|\
    "git@github.com:$EXPECTED_REPO.git")
        ;;
    *)
        fail "Remote '$EXPECTED_REMOTE' does not point exactly to '$EXPECTED_REPO'."
        ;;
esac

if git diff --name-only --diff-filter=U | grep -q .; then
    fail "Unresolved Git merge conflicts were detected."
fi

echo
echo "Current Git status:"
echo
git status --short

if [[ -z "$(git status --porcelain)" ]]; then
    echo "  Working tree is currently clean."
fi

echo
echo "Repository verification succeeded."
echo
read -r -p "Press ENTER to continue to the strict Sphinx build, or Ctrl-C to abort."

echo
echo "------------------------------------------------------------"
echo "2. BUILDING THE PORTAL"
echo "------------------------------------------------------------"
echo

echo "Removing the previous local build..."
rm -rf -- "$BUILD_DIR"

echo "Building the Portal..."
/usr/bin/python3 -m sphinx -W --keep-going -E -a -b html docs "$BUILD_DIR"

echo
echo "Build completed successfully."
echo "No Sphinx warnings were detected."

echo
echo "------------------------------------------------------------"
echo "3. REVIEWING AND STAGING CHANGES"
echo "------------------------------------------------------------"
echo

git status --short

if [[ -z "$(git status --porcelain)" ]]; then
    echo
    echo "No source changes were detected. There is nothing to publish."
    exit 0
fi

echo
echo "Review the complete list above carefully."
echo "All listed changes, including deletions and new files, will be staged."
echo

if ! confirm "Stage all these changes?"; then
    echo
    echo "Publication cancelled before staging."
    exit 0
fi

git add -A

echo
echo "Files staged for the commit:"
echo
git status --short
echo
git --no-pager diff --cached --stat

if git diff --cached --quiet; then
    echo
    echo "Nothing is staged. There is nothing to publish."
    exit 0
fi

echo
echo "------------------------------------------------------------"
echo "4. CREATING THE COMMIT"
echo "------------------------------------------------------------"
echo

read -r -p "Commit message: " COMMITMSG

[[ -n "${COMMITMSG//[[:space:]]/}" ]] || \
    fail "No commit message was entered. Files remain staged."

echo
echo "Commit message:"
echo "  $COMMITMSG"
echo

if ! confirm "Create this commit?"; then
    echo
    echo "Commit cancelled. Files remain staged but nothing was committed or pushed."
    exit 0
fi

git commit -m "$COMMITMSG"

echo
echo "Commit created successfully:"
git --no-pager log -1 --oneline

if [[ -n "$(git status --porcelain)" ]]; then
    echo
    git status --short
    fail "The working tree changed during the commit. Review it before pushing."
fi

echo
echo "------------------------------------------------------------"
echo "5. FINAL PILOT PUBLICATION CHECK"
echo "------------------------------------------------------------"
echo
echo "Repository : $EXPECTED_REPO"
echo "Remote     : $EXPECTED_REMOTE"
echo "Branch     : $EXPECTED_BRANCH"
echo "Commit     : $(git log -1 --oneline)"
echo
echo "Command that will run:"
echo "  git push $EXPECTED_REMOTE $EXPECTED_BRANCH"
echo

if ! confirm "Publish this commit to the PERSONAL PILOT repository now?"; then
    echo
    echo "Publication stopped before the push."
    echo "The commit exists locally but has not been published."
    exit 0
fi

git push "$EXPECTED_REMOTE" "$EXPECTED_BRANCH"

echo
echo "============================================================"
echo "PILOT PUBLICATION COMPLETED SUCCESSFULLY"
echo "============================================================"
echo
echo "Repository: https://github.com/$EXPECTED_REPO"
echo "Website   : https://mih-aqteam.github.io/AQ_portal_pilot/"
echo
echo "After GitHub Pages finishes deploying, validate the pilot site."
echo "Only then run:"
echo
echo "  ./publish_eea.sh"
echo
echo "============================================================"
