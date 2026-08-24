#!/bin/sh
# Run old_target_check.py against a python:<target>-slim container with the built wheel; args: <target> <mode>.
set -eu
TARGET="$1"
MODE="$2"
docker run --rm -e TARGET="$TARGET" -e MODE="$MODE" -v "$PWD:/repo:ro" -v "$(dirname "$(command -v uv)"):/uv-bin:ro" \
  "python:$TARGET-slim" \
  sh -c '/uv-bin/uv run -q --python 3.13 --isolated --no-project --with /repo/dist/*.whl python /repo/tasks/old_target_check.py "$TARGET" "$MODE"'
