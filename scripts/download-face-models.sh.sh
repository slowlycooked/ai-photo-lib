#!/usr/bin/env bash
set -euo pipefail
AI_PHOTO_LIB_MODEL_ROOT=/Users/unclema/models

MODEL_ROOT="${AI_PHOTO_LIB_MODEL_ROOT:-/opt/ai-photo-lib/models}"
FACE_MODEL_DIR="$MODEL_ROOT/face"

mkdir -p "$FACE_MODEL_DIR/yunet"
mkdir -p "$FACE_MODEL_DIR/sface"

curl -L \
  -o "$FACE_MODEL_DIR/yunet/face_detection_yunet_2023mar.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"

curl -L \
  -o "$FACE_MODEL_DIR/sface/face_recognition_sface_2021dec.onnx" \
  "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"

echo "Face models downloaded to: $FACE_MODEL_DIR"