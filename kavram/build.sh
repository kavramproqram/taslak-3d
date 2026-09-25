#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
cc -O3 -fPIC -shared file_engine.c     -o build/libfile_engine.so  -pthread -lm
cc -O3 -fPIC -shared view_engine.c     -o build/libview_engine.so  -pthread -lm
cc -O3 -fPIC -shared kavram3d_engine.c -o build/libkavram3d.so     -pthread -lm
echo "[build] OK"
