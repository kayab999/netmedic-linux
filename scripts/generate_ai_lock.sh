#!/usr/bin/env bash
# Generate netmedic_ai/requirements.lock with hashes from the PyPI sdist.
# Run in CI (linux x86_64, cp312) and commit the result. Never edit by hand.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --upgrade pip-tools
pip-compile --generate-hashes --output-file netmedic_ai/requirements.lock netmedic_ai/pyproject.toml
echo "Generated netmedic_ai/requirements.lock (review before committing)"
