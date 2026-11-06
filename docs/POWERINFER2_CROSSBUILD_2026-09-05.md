# PowerInfer-2 Android sparse-runtime cross-build — 2026-09-05

Host-side Step 1 only. No phone contact, no root, no Termux compile, no
WireGuard/Redis-ACL farm, no Equal Shares, no ComfyUI, no GPU, no model
download.

This file is the hash record. It does **not** overwrite
`docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`.

## Pin status (why the TODO checkbox stays open)

The plan names the upstream repo and the SmallThinker Android recipe, but it
does **not** name a commit/tag or an NDK version (`$HOME/Android/Sdk/ndk/<pinned-ndk-version>`).
This build therefore had to choose both. The binary and hashes below are real;
the TODO item stays unchecked until the operator accepts these two choices as
the pin.

| Choice | Value used | Why |
|---|---|---|
| Source repo | `https://github.com/Tiiny-AI/PowerInfer.git` | Exact URL in the plan. |
| Commit | `8bd56d69906c9d2dba4d3bf6899763401e01a9a4` | HEAD of the project's existing `external/PowerInfer` clone (`Update README.md (#280)`, 2026-05-11). Not a tag. Plan has no SHA; `main` was **not** pulled. |
| NDK | r27d / `Pkg.Revision=27.3.13750724` | Plan left a placeholder. Latest Android NDK **LTS** on 2026-09-05. Official Linux zip SHA-1 matched Google's listing. |

No model or expert bundle was fetched. Step 2 still owns
`huihui-ai/SmallThinker-3B-Preview-abliterated`.

## Host

- WSL2 Ubuntu 24.04.4 LTS, `x86_64` (`Linux DuranGamingPC 6.6.87.2-microsoft-standard-WSL2`)
- `cmake 3.28.3`, `ninja 1.11.1`, `git 2.43.0`, 16 cores
- Build tree: `/root/powerinfer2-android-crossbuild/` (ext4, not NTFS)
- Replay script: `scripts/crossbuild_powerinfer2_android.sh`

## Target (Pixel 10 / Tensor G5)

Tensor G5 is ARM-based (Geekbench/Android Central: 1× Cortex-X4 + 5× Cortex-A725
+ 2× Cortex-A520, AArch64, NEON/SVE/i8mm/dotprod). It is **not** Qualcomm
Hexagon/QNN.

| Item | Value |
|---|---|
| ABI | `arm64-v8a` |
| API | `android-34` |
| Clang/target triple | `aarch64-linux-android34` (`aarch64-linux-android` + API 34) |
| `-march` | `armv8.6-a` (plan/upstream Android recipe; not proven optimal on Tensor G5 until a phone run) |
| Interpreter | `/system/bin/linker64` |

## Source

```
repo:    https://github.com/Tiiny-AI/PowerInfer.git
commit:  8bd56d69906c9d2dba4d3bf6899763401e01a9a4
libaio:  5a546a834c36070648158d19dd564762d59f8eb8  (smallthinker/powerinfer/third_part/libaio)
liburing: f2b6fb85b79baf17f2c0ea24a357c652caa2d7ba (smallthinker/powerinfer/third_part/liburing)
```

Checked out with `git checkout -f 8bd56d69906c9d2dba4d3bf6899763401e01a9a4` from
a clone of `external/PowerInfer`, then `git submodule update --init` for libaio
and liburing only. Internal `libaz` already vendors fmt and Perfetto SDK.

## NDK

```
package:  android-ndk-r27d-linux.zip
url:      https://dl.google.com/android/repository/android-ndk-r27d-linux.zip
size:     663956036 bytes
SHA-1:    22105e410cf29afcf163760cc95522b9fb981121
          (matches https://developer.android.com/ndk/downloads LTS table)
SHA-256:  601246087a682d1944e1e16dd85bc6e49560fe8b6d61255be2829178c8ed15d9
revision: 27.3.13750724
release:  r27d
host tools: linux-x86_64
```

Private copy under `/root/powerinfer2-android-crossbuild/ndk/android-ndk-r27d`.
libaio/liburing were installed into **that copy's** sysroot only.

## Build commands

libaio / liburing (from `smallthinker/powerinfer/third_part`, NDK clang):

```sh
export NDK=/root/powerinfer2-android-crossbuild/ndk/android-ndk-r27d
export TOOLCHAIN=$NDK/toolchains/llvm/prebuilt/linux-x86_64
export TARGET=aarch64-linux-android API=34
export CC=$TOOLCHAIN/bin/${TARGET}${API}-clang
export CXX=$TOOLCHAIN/bin/${TARGET}${API}-clang++
export AR=$TOOLCHAIN/bin/llvm-ar RANLIB=$TOOLCHAIN/bin/llvm-ranlib STRIP=$TOOLCHAIN/bin/llvm-strip
export AS=$CC LD=$TOOLCHAIN/bin/ld HOST=$TARGET
make -C libaio prefix=$TOOLCHAIN/sysroot/usr install
( cd liburing && ./configure --prefix=$TOOLCHAIN/sysroot/usr && make install )
```

Sparse runtime (from `smallthinker/`):

```sh
cmake -S . -B build_android -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-34 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_SHARED_LIBS=OFF \
  -DGGML_OPENMP=OFF -DLLAMA_CURL=OFF -DAZ_ENABLE_PERFETTO=ON \
  -DPOWERINFER_NO_FFN_REPACK=ON -DDISABLE_ARM_FEATURE_CHECK=ON \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=OFF \
  -DCMAKE_C_FLAGS="-march=armv8.6-a -D__USE_GNU -Ofast -flto" \
  -DCMAKE_CXX_FLAGS="-march=armv8.6-a -D__USE_GNU -Ofast -flto"
cmake --build build_android --target llama-cli -j"$(nproc)"
```

The three `LLAMA_BUILD_*=OFF` flags are extra vs the plan: they skip tests,
examples, and the server so only `llama-cli` is requested. They do not change
the Android ABI, march, or sparse flags. CMake reported
`Found liburing, it will be added for static linking.`

## Artifacts

Directory:
`artifacts/powerinfer2_android_arm64/2026-09-05/`

| File | SHA-256 | Bytes | Notes |
|---|---|---|---|
| `llama-cli` | `3b902e1c53f5a2c1c6c8fc1268dee0a0e09917cbe154cb006a007c8667ae8349` | 65383032 | ELF64 AArch64 PIE, RelWithDebInfo, not stripped. BuildID `7038d8d77d8156417173e0cdf6e0470a72dfa364` |
| `libaio.so.1.0.1` | `2b09131bb414b31e37cfb125054e94979c83b021f356576d246eeb9dbcca1f5f` | 21464 | Companion; `llama-cli` `NEEDED`s `libaio.so.1`. Not a phone install. |

Machine-readable copy of the same pins: `BUILD_PIN.txt` in that directory.

### `llama-cli` dynamic NEEDED

```
libm.so
libdl.so
libaio.so.1
liblog.so
libc.so
```

`liburing` is not in `NEEDED` (static). `libm`/`libdl`/`liblog`/`libc` are
Android bionic. Step 2 must ship `libaio.so.1` next to the binary or the
loader will fail on the phone.

## Host smoke test (no phone, no emulator)

Not executed under qemu: the ELF interpreter is `/system/bin/linker64` (Android
bionic), so a glibc `qemu-aarch64` run would not prove anything.

Integrity checks that did run on the x86_64 host:

- `file`: `ELF 64-bit LSB pie executable, ARM aarch64`, dynamically linked
- `readelf -h`: `Machine: AArch64`, `Type: DYN (PIE)`
- `readelf -d`: NEEDED list above
- SHA-256 of the copied artifact matches the build-tree binary

## Deliberate non-actions

- No `adb`, no Termux, no Pixel contact
- No model/GGUF/bundle download (21B Q4_0 or 3B-Preview-abliterated)
- No expert-bundle generation
- NDK clang-21/mold host compilers from the x86 recipe were not used; the NDK
  toolchain compiled the Android binary
- Plan doc left unchanged
