#!/bin/sh
# rtls_common のネイティブテストをビルドして実行する (ローカル / CI 共用)。
set -e
cd "$(dirname "$0")"
CXX="${CXX:-c++}"
"$CXX" -std=c++17 -Wall -Wextra -Werror -I ../lib/rtls_common \
    -o test_rtls_common test_rtls_common.cpp
./test_rtls_common
