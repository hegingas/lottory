#!/usr/bin/env bash
# build_core.sh — 纯逻辑层构建（无需 SystemC）
# 用法: bash model/scripts/build_core.sh [clean]
set -e
cd "$(dirname "$0")/.."

CXX="${CXX:-g++}"
CXXFLAGS="-std=c++17 -Wall -Wextra -O2 -Iinclude"
SRCS="src/pcie_types.cpp src/tlp_ext.cpp src/tlp_builder.cpp src/tlp_parser.cpp src/pending_table.cpp src/memory_map.cpp"

if [ "$1" = "clean" ]; then
  rm -rf build
  echo "cleaned"
  exit 0
fi

mkdir -p build
echo "==> 编译纯逻辑层..."
$CXX $CXXFLAGS -c $SRCS
mkdir -p build/obj
mv *.o build/obj/

echo "==> 编译冒烟测试..."
$CXX $CXXFLAGS tests/test_tlp.cpp build/obj/*.o -o build/test_tlp

echo "==> 运行测试..."
./build/test_tlp
