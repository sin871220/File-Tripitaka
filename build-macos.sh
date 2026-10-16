#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this script on macOS.' >&2
  exit 1
fi

# Use a python.org Python 3.12 installation with Tcl/Tk included.
# For an Intel build, run from an Intel Python on an Intel Mac/runner.
build_python="${FILETRIPITAKA_BUILD_PYTHON:-python3.12}"
"$build_python" -m venv .venv-macos
.venv-macos/bin/python -m pip install -r requirements.txt -r requirements-build.txt
.venv-macos/bin/python scripts/build_release.py --platform macos "$@"
