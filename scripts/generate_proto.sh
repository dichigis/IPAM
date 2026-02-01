#!/bin/bash
# Генерация Python кода из proto файлов

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_ROOT/src/proto"
OUT_DIR="$PROJECT_ROOT/src/ipam/proto_gen"

mkdir -p "$OUT_DIR"

python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    "$PROTO_DIR/ipam.proto"

# Создаем __init__.py
touch "$OUT_DIR/__init__.py"

echo "Proto files generated in $OUT_DIR"
