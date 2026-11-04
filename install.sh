#!/usr/bin/env bash
# Ember — Copyright (C) 2026 Ember contributors.
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Ember needs Python 3.11 or newer. Install python3 and python3-venv using your package manager.\n' >&2
  exit 1
fi
exec python3 "$root/packaging/terminal_installer.py" "$@"
