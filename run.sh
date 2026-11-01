#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ ! -x .venv/bin/python ]; then
  # macOS ships Python 3.9, which cannot install the pinned dependencies.
  # Prefer a Homebrew Python 3.12+ when one is present.
  case "$(uname -s)" in Darwin) export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH" ;; esac
  python=""
  for candidate in python3.14 python3.13 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      python="$candidate"
      break
    fi
  done
  if [ -z "$python" ]; then
    echo "GR Studio needs Python 3.12 or newer. On macOS run: brew install python@3.14" >&2
    exit 1
  fi
  "$python" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m gr_studio "$@"
