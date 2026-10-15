#!/bin/bash
set -e
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -c 'import sys; assert sys.version_info >= (3,12), "需要 Python 3.12 或更新版本"'
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -r requirements.lock --disable-pip-version-check
.venv/bin/python -m waypoint.launcher
