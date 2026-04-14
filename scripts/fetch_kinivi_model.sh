#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="${1:-tello_call/model/keypoint_classifier}"
mkdir -p "$DEST_DIR"

URL="https://github.com/kinivi/tello-gesture-control/raw/refs/heads/main/model/keypoint_classifier/keypoint_classifier.tflite"
OUT="$DEST_DIR/keypoint_classifier.tflite"

echo "Downloading kinivi keypoint classifier model to: $OUT"
if command -v curl >/dev/null 2>&1; then
  curl -L "$URL" -o "$OUT"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$OUT" "$URL"
else
  echo "Neither curl nor wget is available." >&2
  exit 1
fi

echo "Done."
