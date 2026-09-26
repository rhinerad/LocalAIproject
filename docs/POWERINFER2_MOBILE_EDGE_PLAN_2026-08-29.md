# Mobile edge evaluation — Pixel 10 Pro / PowerInfer-2

## Status and non-negotiable scope

This is an **unlaunched evaluation plan**, not a claim that PowerInfer-2 runs
on this phone today. It does not authorize a model download, Android rooting,
an NDK install, a public listener, Redis exposure, or a background service.
The Equal Shares renderer and ComfyUI stay outside this work.

The original PowerInfer-2 paper describes a heterogeneous NPU/CPU design with
I/O-aware caching. That paper is useful research context, but it is not itself
a reproducible Pixel build recipe. The currently documented upstream Android
path is the newer sparse **SmallThinker** runtime inside the PowerInfer
repository. It targets arm64 Android with the NDK, `libaio`, `liburing`, and a
sparse Q4_0 model. It does **not** document an NNAPI, Qualcomm QNN, or Hexagon
build flag. See the [PowerInfer-2 paper](https://arxiv.org/abs/2406.06282) and
the upstream [SmallThinker Android guide](https://github.com/Tiiny-AI/PowerInfer/blob/main/smallthinker/README.md).

The Pixel 10 Pro uses Google Tensor G5 with a Google TPU, not a Qualcomm SoC.
Therefore a Qualcomm Hexagon/QNN delegate is not an available target on this
device. NNAPI is only a generic Android API; without an upstream PowerInfer
NNAPI backend and a Tensor-compatible driver path, enabling it would not prove
that inference left the CPU. Google lists Tensor G5 and 16 GB RAM in the
[official specifications](https://store.google.com/product/pixel_10_pro_specs?hl=en-US).

**Decision:** the intended Pixel deployment model is
`Tiiny/SmallThinker-21BA3B-Instruct-GGUF`'s exact
`SmallThinker-21B-A3B-Instruct.Q4_0.gguf` sparse artifact. It is the highest-
capacity upstream SmallThinker option that the runtime explicitly supports in
Q4_0, with a documented 8 GiB limited-memory configuration. The model file is
about 12.2 GB, while upstream reports 11.47 GiB for normal sparse 21B runtime;
that does **not** guarantee Pixel fit once Android and Termux overhead are
included. Its documented limited-memory path is therefore the planned operating
mode, subject to an actual thermal/throughput test and without rooting the phone.

`Tiiny/SmallThinker-4BA0.6B-Instruct-GGUF`'s exact Q4_0 artifact remains a
mandatory smoke-test model only. It validates the cross-built binary, Q4_0
format, UFS bundle, and thermal controls before the 21B artifact is copied.
It is not the selected final phone model.

**Superseded for the first benign phone test, 2026-09-05:** the TODO.md
step-2 test item now names `huihui-ai/SmallThinker-3B-Preview-abliterated`
instead of a generic "compatible 4B sparse model," chosen for
runtime-compatible provenance already used elsewhere in this stack. See
`CHANGELOG/2026-09-05c_pixel_edge_model_choice.md`. This does not change
the 21B deployment target above; it only changes which model runs the
first smoke test. A separate TODO item tracks abliterating the official
4BA0.6B checkpoint later to close the size gap.

## Locked build pins, 2026-09-05

The exact PowerInfer commit and NDK version below were placeholders
(`<pinned-ndk-version>`, no commit) until this date. They are now the
project's accepted pins for this runtime — do not silently drift to a
newer `main` or a different NDK without a new dated entry here.

- Repo: `https://github.com/Tiiny-AI/PowerInfer.git`
- Commit: `8bd56d69906c9d2dba4d3bf6899763401e01a9a4` (external/PowerInfer HEAD
  as of 2026-05-11; not an upstream tag)
- NDK: r27d / 27.3.13750724 (linux-x86_64), zip SHA-256
  `601246087a682d1944e1e16dd85bc6e49560fe8b6d61255be2829178c8ed15d9`
- Cross-built `llama-cli` SHA-256:
  `3b902e1c53f5a2c1c6c8fc1268dee0a0e09917cbe154cb006a007c8667ae8349`
  (65,383,032 bytes, ELF64 AArch64 PIE, `aarch64-linux-android34`)
- Full hash record: `docs/POWERINFER2_CROSSBUILD_2026-09-05.md`
- Binary + pins on disk: `artifacts/powerinfer2_android_arm64/2026-09-05/`
- Replay script: `scripts/crossbuild_powerinfer2_android.sh`
- Evidence: `CHANGELOG/2026-09-05i_powerinfer2_android_crossbuild.md`

Built on WSL, not in Termux; not run on a phone. `-march=armv8.6-a` is
carried over from this doc's original recipe and is still unproven optimal
for Tensor G5 until a real phone run — see Phase B's existing caution.

Begin with a reproducible CPU-plus-UFS sparse-runtime benchmark. Treat NPU
usage as blocked until upstream publishes a Tensor/NNAPI backend and hardware
counters demonstrate accelerator execution. Do not root the phone to work
around the documented memory-efficient-mode limitation.

## Architecture boundary

```text
Pixel / Termux
  sparse runtime + small, approved model
          |
          |  mTLS or private-overlay HTTPS, per-phone token
          v
Workstation edge gateway (future, loopback/private overlay only)
  validates capability, size, lease, and result
          |
          |  local-only authenticated Redis/Celery
          v
Existing worker farm
```

The phone must **not** receive the farm Redis password, AES key, or direct
Celery access. A lost or compromised phone with those credentials could claim,
inspect, or poison workstation work. The initial phone allowlist is one small,
non-sensitive `edge_text_inference` job with a 12,000-character prompt and a
512-token cap. No historical chat exports, raw artifacts, rendering, commands,
file edits, model downloads, or decryption are phone jobs.

`local_agent/worker_farm/termux_powerinfer2_edge_worker.py` expresses this
gateway contract. It is disabled by default and its gateway endpoints do not
exist yet; it intentionally cannot connect to Redis.

## Phase A — phone inventory and thermal acceptance

Run these only from Termux after installing Termux:API if battery telemetry is
wanted. They are diagnostic, not build steps:

```sh
pkg update
pkg install python git curl coreutils openssl-tool
termux-battery-status
getprop ro.product.cpu.abi
getprop ro.build.version.sdk
df -h "$HOME"
```

Record: Android API level, free internal storage, battery state, and a
10-minute sustained CPU temperature/battery observation. Start with one model
and one process. Stop when charging is disconnected, battery is below 40%, or
the device reports thermal throttling.

## Phase B — supported Android compile path

Do the NDK cross-build on an **x86_64 Linux or WSL build host**, not inside
Termux. Android's documented NDK host tools are `linux-x86_64`; they cannot run
natively on the phone's arm64 userspace. A pure Termux/clang compile may be an
experiment, but it is CPU-only and is not the upstream sparse Android path.

Prerequisites on the build host:

```sh
sudo apt update
sudo apt install -y git cmake ninja-build clang-21 mold make python3 python3-venv
git clone --recurse-submodules https://github.com/Tiiny-AI/PowerInfer.git
cd PowerInfer
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd smallthinker
export NDK="$HOME/Android/Sdk/ndk/27.3.13750724"  # r27d, locked 2026-09-05
export TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/linux-x86_64"
export TARGET=aarch64-linux-android
export API=34
```

Build the two upstream dependencies into the NDK sysroot. Pin and record the
PowerInfer commit and NDK version before accepting a binary:

```sh
cd ../powerinfer/third_part/libaio
export HOST="$TARGET" AR="$TOOLCHAIN/bin/llvm-ar"
export CC="$TOOLCHAIN/bin/$TARGET$API-clang" AS="$CC"
export CXX="$TOOLCHAIN/bin/$TARGET$API-clang++"
export LD="$TOOLCHAIN/bin/ld" RANLIB="$TOOLCHAIN/bin/llvm-ranlib"
export STRIP="$TOOLCHAIN/bin/llvm-strip"
make prefix="$TOOLCHAIN/sysroot/usr" install

cd ../liburing
./configure --prefix="$TOOLCHAIN/sysroot/usr"
make install

cd ../../../../smallthinker
cmake -S . -B build_android -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-34 \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_SHARED_LIBS=OFF \
  -DGGML_OPENMP=OFF -DLLAMA_CURL=OFF -DAZ_ENABLE_PERFETTO=ON \
  -DPOWERINFER_NO_FFN_REPACK=ON -DDISABLE_ARM_FEATURE_CHECK=ON \
  -DCMAKE_C_FLAGS="-march=armv8.6-a -D__USE_GNU -Ofast -flto" \
  -DCMAKE_CXX_FLAGS="-march=armv8.6-a -D__USE_GNU -Ofast -flto"
cmake --build build_android --target llama-cli -j"$(nproc)"
```

Before deployment, calculate a SHA-256 of `llama-cli`, record the source
commit, and scan its dynamic dependencies. Copy only that known binary to
Termux with USB/ADB or an operator-approved immutable download:

```sh
adb push build_android/bin/llama-cli /data/local/tmp/llama-cli
adb shell chmod 700 /data/local/tmp/llama-cli
adb shell sha256sum /data/local/tmp/llama-cli
```

Do not claim `-march=armv8.6-a` is optimal for Tensor G5 until the phone binary
actually runs. If it fails an instruction check, rebuild with a lower proven
architecture level rather than disabling checks permanently.

## Phase C — model and UFS layout

PowerInfer-2/SmallThinker needs a sparse-compatible model format; a normal
Ollama GGUF, arbitrary Qwen GGUF, or dense 70B model is not an upgrade path.
For the current documented runtime, use only an upstream-compatible sparse Q4_0
model. The deployment target is the selected SmallThinker 21B Q4_0 artifact;
the 4B Q4_0 artifact is used first only to validate the runtime. Do not replace
either with a normal Ollama GGUF, arbitrary Qwen GGUF, or dense 70B model. The
upstream conversion path is:

```sh
python3 convert_hf_to_gguf.py /path/to/safetensors_model \
  --outtype f16 --outfile /path/to/model_f16.gguf --transpose-down all
./build_android/bin/llama-quantize --pure /path/to/model_f16.gguf \
  /path/to/model_q4_0.gguf Q4_0 8
```

For constrained memory, first generate an immutable expert bundle, then create
a no-MoE-weight GGUF. Keep both files together and checksum them:

```sh
GENERATE_EXPERT_BUNDLE=/secure/path/expert.bundle ./build_android/bin/llama-cli \
  -m /secure/path/model_q4_0.gguf --no-cnv -t 2 -n 32 -p "health check"
python3 get_no_moe_weights_ffn.py /secure/path/model_q4_0.gguf \
  /secure/path/model_no_moe_q4_0.gguf
sha256sum /secure/path/model_q4_0.gguf /secure/path/model_no_moe_q4_0.gguf \
  /secure/path/expert.bundle > /secure/path/SHA256SUMS
```

On the phone, store only validated model, bundle, checksums, and short-lived
job scratch data under Termux private storage, for example
`$HOME/.local/share/powerinfer/`. Avoid shared `/sdcard` paths for model cache
or sensitive job output. Maintain at least 20% free UFS capacity, keep one
runtime process, use a 2–4 thread starting point, and benchmark only from a
cool, charging state. `MAX_N_CACHED=768` is the upstream SmallThinker 4B
starting example; it is a benchmark parameter, not a guaranteed Pixel value.

The upstream guide says the memory-efficient Termux route may require root.
That is a stop gate, not permission to root a personal phone. Test normal sparse
mode first; if it cannot fit or meet throughput at safe thermals, keep the
phone as a lightweight preprocessing edge node.

## Phase D — controlled worker acceptance

After the private overlay and gateway are implemented and independently tested,
copy the binary/model under the paths chosen above and run exactly one benign
job:

```sh
chmod 600 "$HOME/.config/local-agent/edge-token"
python "$HOME/local_agent/termux_powerinfer2_edge_worker.py" \
  --gateway "https://<private-overlay-workstation-host>" \
  --token-file "$HOME/.config/local-agent/edge-token" \
  --binary "$HOME/.local/bin/llama-cli" \
  --model "$HOME/.local/share/powerinfer/model_no_moe_q4_0.gguf" \
  --threads 2 --once
```

Acceptance requires: one claimed benign task, one bounded result, no Redis
credential on the phone, no raw artifact content in logs, no model process
after completion, and a verified phone thermal/battery result. Add polling
only after that test, and allow only a 15-second-or-longer interval.

## Deferred work

- Implement a private-overlay, mTLS-capable edge gateway with per-device
  capability tokens, lease/idempotency, replay refusal, result-size limits, and
  revocation.
- Independently validate the upstream mobile binary and the 4B sparse smoke-test
  model on the Pixel before copying the selected 21B Q4_0 target. Do not source
  a 47B/70B experiment from the paper as a production phone workload.
- Identify a supported Tensor G5 accelerator backend only if upstream provides
  it, then demonstrate NPU use with device-level telemetry. No Qualcomm QNN or
  Hexagon instructions apply to this Tensor device.
