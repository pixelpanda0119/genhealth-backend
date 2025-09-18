#!/bin/bash

echo "[runtime] Linking missing shared libs..."

GL=$(find /nix/store -name 'libGL.so.1' | head -n 1)
GLIB=$(find /nix/store -name 'libglib-2.0.so.0' | head -n 1)
GTHREAD=$(find /nix/store -name 'libgthread-2.0.so.0' | head -n 1)

ln -sf "$GL" /usr/lib/libGL.so.1
ln -sf "$GLIB" /usr/lib/libglib-2.0.so.0
ln -sf "$GTHREAD" /usr/lib/libgthread-2.0.so.0

echo "[runtime] Running app..."
exec "$@"