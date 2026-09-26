#!/usr/bin/env bash
# Host-side Android NDK cross-build of the SmallThinker/PowerInfer-2 sparse
# runtime (llama-cli) for arm64-v8a. No phone contact, no model download.
set -euo pipefail

PINNED_REPO_URL="https://github.com/Tiiny-AI/PowerInfer.git"
PINNED_COMMIT="8bd56d69906c9d2dba4d3bf6899763401e01a9a4"
NDK_RELEASE="r27d"
NDK_PACKAGE="android-ndk-${NDK_RELEASE}-linux.zip"
NDK_URL="https://dl.google.com/android/repository/${NDK_PACKAGE}"
# Official SHA-1 from https://developer.android.com/ndk/downloads (LTS r27d).
NDK_ZIP_SHA1_OFFICIAL="22105e410cf29afcf163760cc95522b9fb981121"
ANDROID_ABI="arm64-v8a"
ANDROID_API="34"
TARGET_TRIPLE="aarch64-linux-android"
MARCH="armv8.6-a"

WORK="${WORK:-/root/powerinfer2-android-crossbuild}"
PROJECT_ROOT="${PROJECT_ROOT:-/mnt/a/Users/rhine/Documents/Codex/2026-08-07/referenced-chatgpt-conversation-this-is-an-2/COMFYUI_STORY_HANDOFF_2026-08-09}"
LOCAL_MIRROR="${LOCAL_MIRROR:-${PROJECT_ROOT}/external/PowerInfer}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DATE_DAY="$(date -u +%Y-%m-%d)"
ARTIFACT_DIR="${PROJECT_ROOT}/artifacts/powerinfer2_android_arm64/${DATE_DAY}"
STATUS_FILE="${WORK}/STATUS"
LOG="${WORK}/logs/build.log"

mkdir -p "${WORK}/downloads" "${WORK}/logs" "${WORK}/ndk" "${ARTIFACT_DIR}"
exec > >(tee -a "${LOG}") 2>&1

status() { printf '%s\n' "$1" > "${STATUS_FILE}"; }
die() { status "FAILED: $*"; echo "FAILED: $*" >&2; exit 1; }

status "RUNNING: start ${STAMP}"
echo "=== PowerInfer-2 Android cross-build ${STAMP} ==="
echo "host=$(uname -a)"
echo "nproc=$(nproc)"
echo "cmake=$(cmake --version | head -1)"
echo "ninja=$(ninja --version)"
echo "git=$(git --version)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  git cmake ninja-build make python3 python3-venv python3-pip \
  unzip wget ca-certificates file binutils xxd patch pkg-config

# --- NDK ---
NDK_ZIP="${WORK}/downloads/${NDK_PACKAGE}"
if [[ ! -f "${NDK_ZIP}" ]]; then
  wget -O "${NDK_ZIP}.partial" "${NDK_URL}"
  mv "${NDK_ZIP}.partial" "${NDK_ZIP}"
fi
NDK_ZIP_SHA1="$(sha1sum "${NDK_ZIP}" | awk '{print $1}')"
NDK_ZIP_SHA256="$(sha256sum "${NDK_ZIP}" | awk '{print $1}')"
echo "NDK zip SHA1=${NDK_ZIP_SHA1}"
echo "NDK zip SHA256=${NDK_ZIP_SHA256}"
[[ "${NDK_ZIP_SHA1}" == "${NDK_ZIP_SHA1_OFFICIAL}" ]] || die "NDK SHA-1 mismatch: got ${NDK_ZIP_SHA1} expected ${NDK_ZIP_SHA1_OFFICIAL}"

NDK="${WORK}/ndk/android-ndk-${NDK_RELEASE}"
if [[ ! -f "${NDK}/source.properties" ]]; then
  rm -rf "${NDK}"
  unzip -q "${NDK_ZIP}" -d "${WORK}/ndk"
fi
[[ -f "${NDK}/source.properties" ]] || die "NDK extract missing source.properties"
echo "----- NDK source.properties -----"
cat "${NDK}/source.properties"
TOOLCHAIN="${NDK}/toolchains/llvm/prebuilt/linux-x86_64"
[[ -x "${TOOLCHAIN}/bin/${TARGET_TRIPLE}${ANDROID_API}-clang" ]] || die "missing NDK clang ${TARGET_TRIPLE}${ANDROID_API}-clang"

# --- Source at pinned commit ---
SRC="${WORK}/src/PowerInfer"
if [[ ! -d "${SRC}/.git" ]]; then
  mkdir -p "${WORK}/src"
  if [[ -d "${LOCAL_MIRROR}/.git" ]]; then
    git clone --no-checkout "${LOCAL_MIRROR}" "${SRC}"
  else
    git clone --no-checkout "${PINNED_REPO_URL}" "${SRC}"
  fi
fi
cd "${SRC}"
git remote get-url origin >/dev/null 2>&1 || git remote add origin "${PINNED_REPO_URL}"
# Ensure the pinned commit exists; fetch from GitHub if the local mirror lacks it.
if ! git cat-file -e "${PINNED_COMMIT}^{commit}" 2>/dev/null; then
  git fetch --depth 1 origin "${PINNED_COMMIT}"
fi
git checkout -f "${PINNED_COMMIT}"
git reset --hard "${PINNED_COMMIT}"
git clean -fdx -e '/.git'
ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "${ACTUAL_COMMIT}" == "${PINNED_COMMIT}" ]] || die "checkout drifted: ${ACTUAL_COMMIT}"
git submodule sync --recursive
git submodule update --init --recursive -- \
  smallthinker/powerinfer/third_part/libaio \
  smallthinker/powerinfer/third_part/liburing
LIBAIO_SHA="$(git -C smallthinker/powerinfer/third_part/libaio rev-parse HEAD)"
LIBURING_SHA="$(git -C smallthinker/powerinfer/third_part/liburing rev-parse HEAD)"
echo "PowerInfer commit=${ACTUAL_COMMIT}"
echo "libaio submodule=${LIBAIO_SHA}"
echo "liburing submodule=${LIBURING_SHA}"

export NDK TOOLCHAIN
export TARGET="${TARGET_TRIPLE}"
export HOST="${TARGET}"
export API="${ANDROID_API}"
export AR="${TOOLCHAIN}/bin/llvm-ar"
export CC="${TOOLCHAIN}/bin/${TARGET}${API}-clang"
export AS="${CC}"
export CXX="${TOOLCHAIN}/bin/${TARGET}${API}-clang++"
export LD="${TOOLCHAIN}/bin/ld"
export RANLIB="${TOOLCHAIN}/bin/llvm-ranlib"
export STRIP="${TOOLCHAIN}/bin/llvm-strip"
SYSROOT_USR="${TOOLCHAIN}/sysroot/usr"

# --- libaio into this NDK copy's sysroot ---
cd "${SRC}/smallthinker/powerinfer/third_part/libaio"
make distclean >/dev/null 2>&1 || true
make prefix="${SYSROOT_USR}" install

# --- liburing into this NDK copy's sysroot ---
cd "${SRC}/smallthinker/powerinfer/third_part/liburing"
make distclean >/dev/null 2>&1 || true
# configure is a custom script; prefix must land in the NDK sysroot.
./configure --prefix="${SYSROOT_USR}"
make install

# --- cmake Android build ---
cd "${SRC}/smallthinker"
rm -rf build_android
cmake -S . -B build_android -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="${NDK}/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI="${ANDROID_ABI}" \
  -DANDROID_PLATFORM="android-${ANDROID_API}" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DBUILD_SHARED_LIBS=OFF \
  -DGGML_OPENMP=OFF \
  -DLLAMA_CURL=OFF \
  -DAZ_ENABLE_PERFETTO=ON \
  -DPOWERINFER_NO_FFN_REPACK=ON \
  -DDISABLE_ARM_FEATURE_CHECK=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=OFF \
  -DCMAKE_C_FLAGS="-march=${MARCH} -D__USE_GNU -Ofast -flto" \
  -DCMAKE_CXX_FLAGS="-march=${MARCH} -D__USE_GNU -Ofast -flto"
cmake --build build_android --target llama-cli -j"$(nproc)"

BIN="${SRC}/smallthinker/build_android/bin/llama-cli"
[[ -f "${BIN}" ]] || die "llama-cli missing at ${BIN}"

# --- host-side ELF smoke (no phone, no Android emulator) ---
file "${BIN}"
readelf -h "${BIN}"
echo "----- NEEDED -----"
readelf -d "${BIN}" | awk '/NEEDED|SONAME|RPATH|RUNPATH/' || true
echo "----- machine/arch -----"
readelf -A "${BIN}" | head -40 || true
"${TOOLCHAIN}/bin/llvm-readelf" -h "${BIN}" | sed -n '1,20p'
file "${BIN}" | grep -q "ARM aarch64" || file "${BIN}" | grep -q "ARM aarch64" || {
  # GNU file(1) typically says "ELF 64-bit LSB pie executable, ARM aarch64"
  file "${BIN}" | grep -Eiq "aarch64|ARM aarch64" || die "binary is not aarch64: $(file "${BIN}")"
}

BIN_SHA256="$(sha256sum "${BIN}" | awk '{print $1}')"
BIN_SIZE="$(stat -c%s "${BIN}")"
echo "llama-cli SHA256=${BIN_SHA256} size=${BIN_SIZE}"

install -m 0755 "${BIN}" "${ARTIFACT_DIR}/llama-cli"
sha256sum "${ARTIFACT_DIR}/llama-cli" | tee "${ARTIFACT_DIR}/llama-cli.sha256"
cp -a "${NDK}/source.properties" "${ARTIFACT_DIR}/ndk-source.properties"
printf '%s  %s\n' "${NDK_ZIP_SHA256}" "${NDK_PACKAGE}" > "${ARTIFACT_DIR}/ndk-zip.sha256"
printf '%s  %s\n' "${NDK_ZIP_SHA1}" "${NDK_PACKAGE}" > "${ARTIFACT_DIR}/ndk-zip.sha1"
{
  echo "repo_url=${PINNED_REPO_URL}"
  echo "commit=${ACTUAL_COMMIT}"
  echo "libaio_submodule=${LIBAIO_SHA}"
  echo "liburing_submodule=${LIBURING_SHA}"
  echo "ndk_release=${NDK_RELEASE}"
  echo "ndk_package=${NDK_PACKAGE}"
  echo "ndk_url=${NDK_URL}"
  echo "ndk_zip_sha1=${NDK_ZIP_SHA1}"
  echo "ndk_zip_sha256=${NDK_ZIP_SHA256}"
  echo "target_triple=${TARGET_TRIPLE}${ANDROID_API}"
  echo "android_abi=${ANDROID_ABI}"
  echo "android_api=${ANDROID_API}"
  echo "march=${MARCH}"
  echo "llama_cli_sha256=${BIN_SHA256}"
  echo "llama_cli_bytes=${BIN_SIZE}"
  echo "built_utc=${STAMP}"
} | tee "${ARTIFACT_DIR}/BUILD_PIN.txt"

# Record dynamic deps for the hash-record doc
readelf -d "${BIN}" > "${ARTIFACT_DIR}/llama-cli.readelf-d.txt" || true
file "${BIN}" > "${ARTIFACT_DIR}/llama-cli.file.txt"
readelf -h "${BIN}" > "${ARTIFACT_DIR}/llama-cli.readelf-h.txt"

status "DONE"
echo "DONE: artifact ${ARTIFACT_DIR}/llama-cli"
echo "DONE: sha256 ${BIN_SHA256}"
