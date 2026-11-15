#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------------------------
# download_offline_assets.sh
# -------------------------------------------------------------------
# This script should be executed **once** on a machine that has Internet
# access. It downloads all Python wheels required by the project
# (including transitive dependencies) into ./docker/wheels and also
# saves any required non-Python cache files such as the tiktoken
# tokenizer data.
# -------------------------------------------------------------------

# Create directories for wheels and cache assets
mkdir -p docker/wheels
mkdir -p docker/cache

# -------------------------------------------------------------------
# 1. Download Python wheels for the exact requirements
# -------------------------------------------------------------------
pip download -r requirements.txt -d docker/wheels

# -------------------------------------------------------------------
# 2. Download tiktoken cache
# -------------------------------------------------------------------
python3 - <<'PY'
import pathlib, shutil
src = pathlib.Path.home() / ".cache" / "tiktoken"
if src.is_dir():
    dst = pathlib.Path("docker/cache/tiktoken")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    print(f"Copied tiktoken cache to {dst}")
else:
    print("tiktoken cache not found – run a dummy encode locally first.")
PY

echo "Offline assets prepared in ./docker/wheels and ./docker/cache"
