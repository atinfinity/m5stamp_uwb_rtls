#!/bin/sh
# ファームウェア共通ロジックのネイティブテスト (ローカル / CI 共用)。
set -e
cd "$(dirname "$0")"
CXX="${CXX:-c++}"

"$CXX" -std=c++17 -Wall -Wextra -Werror -I ../lib/rtls_common \
    -o test_rtls_common test_rtls_common.cpp
./test_rtls_common

"$CXX" -std=c++17 -Wall -Wextra -Werror -I ../lib/rtls_solver \
    -o test_rtls_solver test_rtls_solver.cpp
./test_rtls_solver

"$CXX" -std=c++17 -Wall -Wextra -Werror -I ../lib/rtls_common \
    -o test_rtls_config test_rtls_config.cpp
./test_rtls_config
