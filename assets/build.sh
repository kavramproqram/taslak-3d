#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
cc -O3 -fPIC -shared file_engine.c     -o build/libfile_engine.so  -pthread -lm
cc -O3 -fPIC -shared view_engine.c     -o build/libview_engine.so  -pthread -lm
cc -O3 -fPIC -shared kavram3d_engine.c -o build/libkavram3d.so     -pthread -lm
echo "[build] OK"

# Python sources are intentionally not bytecode-packaged; Blender/Kavram loads them directly.
python3 -m py_compile Kavram.py pencere.py panel_system.py nomper.py object_panel.py viewport.py scene_import.py scene_io.py native_engine.py categories.py kyol.py ortam.py
echo "[build] Python syntax OK"
