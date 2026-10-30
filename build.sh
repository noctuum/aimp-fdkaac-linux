#!/bin/sh
# Builds fdkaac and the wrapper in the pinned manylinux_2_28 container.
set -eu
cd "$(dirname "$0")"

python3 -I scripts/fetch.py --verify
image_ref=$(python3 -I scripts/fetch.py --print image_ref)
epoch=$(python3 -I scripts/fetch.py --print epoch)
python=$(python3 -I scripts/fetch.py --print python)

# build/probe and build/host hold the host builds the tests run.
mkdir -p build
find build -mindepth 1 -maxdepth 1 ! -name probe ! -name host -exec rm -rf {} +
rm -rf dist
mkdir -p dist

docker run --rm --network none --user "$(id -u):$(id -g)" \
  -e SOURCE_DATE_EPOCH="$epoch" -e PYTHON="$python" \
  -v "$PWD:/work:ro" -v "$PWD/build:/build" -v "$PWD/dist:/dist" \
  "$image_ref" /work/scripts/container-build.sh

sha256sum build/out/fdkaac build/out/fdkaac-aimp
