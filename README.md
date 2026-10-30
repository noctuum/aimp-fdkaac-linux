# aimp-fdkaac-linux

This is the Linux build of the AIMP add-on "AAC/M4A Encoder (FDK)". The package `enc_fdkaac.aimppack` gives the converter of AIMP 6 for Linux on x86-64 three AAC encoders. They run [fdkaac](https://github.com/nu774/fdkaac) 1.0.9 with [libfdk-aac](https://github.com/mstorsjo/fdk-aac) 3.0.0 linked statically.

| Encoder | Sample rates, Hz | Channels | Presets |
|---|---|---|---|
| AAC-LC (FDK) | 8000 to 96000 | 1, 2, 6, 8 | CBR 16 to 576 kbps, VBR 1 to 5 |
| HE-AAC (FDK) | 16000 to 48000 | 1, 2 | CBR 16 to 128 kbps, VBR 1 to 5 |
| HE-AAC v2 (FDK) | 16000 to 48000 | 2 | CBR 16 to 64 kbps, VBR 1 to 5 |

Open the package with AIMP to install it. `package/README.txt` covers installation and removal.

## Package

The AIMP installer takes a package for Linux only when its manifest is in `x64/`, and on install it merges `x64/` into the add-on folder.

| Member | Content |
|---|---|
| `x64/enc_fdkaac.xml` | the manifest of the three encoders |
| `x64/fdkaac-aimp` | the program the converter runs |
| `x64/fdkaac` | `fdkaac` with `libfdk-aac` linked in |
| `README.txt` | requirements, installation, removal |
| `enc_fdkaac.txt` | the catalog description in Russian and English |
| `LICENSE.fdkaac.txt` | `COPYING` of `fdkaac` |
| `LICENSE.fdk-aac.txt` | `NOTICE` of `libfdk-aac` |

## The wrapper

The converter starts the encoders of one batch with the pipes of the other jobs inherited. An encoder that holds the write end of another job's input keeps that job waiting for the end of its input. The installer gives the programs of an add-on mode 0777, and the converter ignores the exit code of an encoder.

`fdkaac-aimp` closes every inherited descriptor above 2, sets mode 0755 on itself and on `fdkaac`, and runs `fdkaac` from its own folder with the same arguments. When `fdkaac` fails, `fdkaac-aimp` removes the output, so the converter reports an error. `fdkaac` and `libfdk-aac` are built from their tag archives with no patch.

## Build

The build needs Docker and Python 3. It runs with no network in `quay.io/pypa/manylinux_2_28_x86_64`, pinned by digest.

```bash
python3 -I scripts/fetch.py --download fdkaac
python3 -I scripts/fetch.py --download fdk-aac
docker pull "$(python3 -I scripts/fetch.py --print image_ref)"
./build.sh
```

`fetch.py` downloads the tag archives into `third_party/`. `build.sh` checks the SHA-256 of each archive and the commit it names against `upstream.json`, builds `libfdk-aac`, `fdkaac` and `fdkaac-aimp` in the container, and writes three files to `dist/`:

- `enc_fdkaac.aimppack`, the package
- `enc_fdkaac.zip`, the same bytes under a `.zip` name
- `enc_fdkaac-1.0.9-src.tar.gz`, the sources of the package with both upstream archives

The binaries link `libc` and `libm` and nothing else, with glibc symbol versions no newer than 2.28.

## Tests

`python3 -m pytest` needs pytest, NumPy, FFmpeg with `ffprobe`, the output of `./build.sh`, the probe kit and two host builds:

```bash
mkdir -p build/probe build/host
cc -std=c11 -O2 -Wall -Wextra -Werror -D_GNU_SOURCE -DPROBE_VARIANT='"test"' -DPROBE_REPORT_DIR='""' -o build/probe/probe probe/probe.c
cc -std=c11 -O2 -Wall -Wextra -Werror -D_GNU_SOURCE -o build/host/fdkaac-aimp wrapper/fdkaac-aimp.c
python3 -I probe/make_kit.py
```

`make_kit.py` needs `cc`, `ffmpeg` and `sox`.

The suite checks the manifest, encodes every combination of preset, sample rate and channel count the way the converter feeds `fdkaac`, checks the channel order at 5.1 and 7.1, and checks the package and the source archive. Two runs stay out of the default one:

```bash
python3 -m pytest -m slow
FDKAAC_REFERENCE=/usr/bin/fdkaac python3 -m pytest tests/test_reference.py
```

The first sends more than 4 GiB through the pipe of one encoder. The second compares the AAC payload with that of another build of `fdkaac`.

## Layout

| Path | Content |
|---|---|
| `package/` | the manifest and the texts of the package |
| `wrapper/` | `fdkaac-aimp.c` |
| `scripts/` | `fetch.py`, `container-build.sh`, `pack.py` |
| `tools/` | the manifest model, the zip writer, the pins, helpers for WAV and M4A |
| `probe/` | the probe encoder that measured how the converter runs an encoder |
| `tests/` | the test suite |
| `upstream.json` | the pins |

## Pins

| Pin | Value |
|---|---|
| `fdkaac` | tag v1.0.9, commit `1b311f7cda11ddabc11bb0e6230506796a6018c5` |
| `libfdk-aac` | tag v3.0.0, commit `a68a51aa45d86a43c7b228e3d45624af09dcdd8d` |
| build image | `quay.io/pypa/manylinux_2_28_x86_64@sha256:e0adf18521ad35192df733a6c62d35df7801957d24e0470238aacecfab2188a3` |
| `SOURCE_DATE_EPOCH` | 1791714862, the commit time of `libfdk-aac` v3.0.0 |

`libfdk-aac` comes from the newest tag that `fdkaac` 1.0.9 builds against and whose output passes the tests. On 2026-10-29 the newest tags of `mstorsjo/fdk-aac` were v3.0.0 and v2.0.3, and v3.0.0 passes. With `FDKAAC_REFERENCE` set to the Arch Linux `fdkaac` 1.0.9 on `libfdk-aac` 3.0.0, the AAC payload is the same byte for byte.
