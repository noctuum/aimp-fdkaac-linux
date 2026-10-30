#!/bin/sh
# Runs in quay.io/pypa/manylinux_2_28_x86_64: builds libfdk-aac and fdkaac from the pinned archives, then the wrapper.
set -eu

mkdir -p /build/src/fdkaac /build/src/fdk-aac /build/wrapper /build/out
# The archive names repeat upstream.json.
tar -xzf /work/third_party/fdkaac-1.0.9.tar.gz -C /build/src/fdkaac --strip-components=1
tar -xzf /work/third_party/fdk-aac-3.0.0.tar.gz -C /build/src/fdk-aac --strip-components=1

cmake -S /build/src/fdk-aac -B /build/fdk-aac -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_PROGRAMS=OFF -DCMAKE_INSTALL_PREFIX=/build/prefix -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_CXX_FLAGS=-DSUPPRESS_BUILD_DATE_INFO
cmake --build /build/fdk-aac -j "$(nproc)"
cmake --install /build/fdk-aac

PKG_CONFIG_PATH=/build/prefix/lib/pkgconfig cmake -S /build/src/fdkaac -B /build/fdkaac -DCMAKE_BUILD_TYPE=Release
cmake --build /build/fdkaac -j "$(nproc)"
strip --strip-all -o /build/out/fdkaac /build/fdkaac/fdkaac

cc -std=c11 -O2 -Wall -Wextra -Werror -D_GNU_SOURCE -o /build/wrapper/fdkaac-aimp /work/wrapper/fdkaac-aimp.c
strip --strip-all -o /build/out/fdkaac-aimp /build/wrapper/fdkaac-aimp

first=$(/build/out/fdkaac --help 2>&1 | head -n 1)
if [ "$first" != "fdkaac 1.0.9" ]; then
  echo "container-build: fdkaac --help starts with: $first" >&2
  exit 1
fi
echo "$first"
