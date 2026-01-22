#!/bin/sh
set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="$ROOT_DIR/ui"
OUT_DIR="$ROOT_DIR/agent/tether/static_ui"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
cp -R "$UI_DIR/dist/"* "$OUT_DIR/"
