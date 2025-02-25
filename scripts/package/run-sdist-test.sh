#!/usr/bin/env bash

# Build the sdist archive, extract it and run the tests.

set -e

rm -rf dist
uv build --sdist
cd dist
SDIST_ARCHIVE=$(echo picard-*.tar.gz)
tar xvf "$SDIST_ARCHIVE"
cd "${SDIST_ARCHIVE%.tar.gz}"
uv run --group test pytest --verbose
