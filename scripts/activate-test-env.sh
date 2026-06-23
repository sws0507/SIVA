#!/usr/bin/env sh

# Source this file from the repository root:
#   . scripts/activate-test-env.sh

SIVA_ROOT="/Users/sunweishi/code/SIVA_project/SIVA"

if [ ! -f "$SIVA_ROOT/.venv/bin/activate" ]; then
  echo "Missing $SIVA_ROOT/.venv/bin/activate" >&2
  return 1 2>/dev/null || exit 1
fi

. "$SIVA_ROOT/.venv/bin/activate"
