#!/usr/bin/env bash
# Compile the isolated SAF pyjnius spike on WSL ext4. Does not adb install.
set -euo pipefail

SRC="${SRC:-/mnt/a/Users/rhine/Documents/Codex/2026-08-07/referenced-chatgpt-conversation-this-is-an-2/COMFYUI_STORY_HANDOFF_2026-08-09/local_agent/saf_pyjnius_spike}"
RECIPES="${RECIPES:-/mnt/a/Users/rhine/Documents/Codex/2026-08-07/referenced-chatgpt-conversation-this-is-an-2/COMFYUI_STORY_HANDOFF_2026-08-09/local_agent/vendor_sideband/recipes}"
WORK="${WORK:-/root/saf-pyjnius-spike}"
VENV="${VENV:-/opt/sideband-build-venv}"
LOG="${WORK}/build.log"
export DEBIAN_FRONTEND=noninteractive
export BUILDOZER_WARN_ON_ROOT=0
# CUDA libs on this host confuse hostpython configure; spike does not need them.
unset LD_LIBRARY_PATH CUDA_HOME

mkdir -p "${WORK}"
# Truncate before any watcher can see a stale BUILD_EXIT from a prior attempt.
: > "${LOG}"
rsync -a --delete \
  --exclude '.buildozer/' --exclude 'bin/' --exclude '__pycache__/' \
  --exclude 'recipes/' \
  "${SRC}/" "${WORK}/"
rsync -a --delete "${RECIPES}/" "${WORK}/recipes/"
# Overlay hostpython3 is an older p4a copy (no .pip). The pinned p4a commit
# expects HostPython3Recipe.pip. Reuse p4a's recipe, pin CPython 3.11.5.
P4A_HOST="${WORK}/.buildozer/android/platform/python-for-android/pythonforandroid/recipes/hostpython3"
if [[ -d "${P4A_HOST}" ]]; then
  rm -rf "${WORK}/recipes/hostpython3"
  cp -a "${P4A_HOST}" "${WORK}/recipes/hostpython3"
  sed -i "s/version = '3.14.2'/version = '3.11.5'/" \
    "${WORK}/recipes/hostpython3/__init__.py"
fi
# p4a git-resets its checkout every run. Keep a patched copy so
# PyProjectRecipe uses native-build hostpython (not the android-build copy).
P4A_CLONE="${WORK}/.buildozer/android/platform/python-for-android"
P4A_SRC="${P4A_SRC:-/root/p4a-safspike}"
if [[ -d "${P4A_CLONE}/.git" && ! -d "${P4A_SRC}/.git" ]]; then
  cp -a "${P4A_CLONE}" "${P4A_SRC}"
fi
if [[ -f "${P4A_SRC}/pythonforandroid/recipe.py" ]]; then
  python3 "${WORK}/patch_p4a_hostpython_interpreter.py" \
    "${P4A_SRC}/pythonforandroid/recipe.py"
  # Must live in [app], not after [buildozer] (Buildozer ignores the latter).
  if ! grep -q '^p4a.source_dir' "${WORK}/buildozer.spec"; then
    sed -i "/^p4a.commit = /a p4a.source_dir = ${P4A_SRC}" \
      "${WORK}/buildozer.spec"
  fi
fi
cd "${WORK}"

{
  echo "=== SAF pyjnius spike build $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "host=$(uname -a)"
  echo "java=$(java -version 2>&1 | tr '\n' ' ')"
  echo "python=$(${VENV}/bin/python3 --version)"
  echo "buildozer=$(${VENV}/bin/buildozer --version)"
  echo "work=${WORK}"
} | tee "${LOG}"

echo "=== apt host deps ===" | tee -a "${LOG}"
apt-get update -y >>"${LOG}" 2>&1
apt-get install -y --no-install-recommends \
  git unzip zip openjdk-21-jdk-headless python3-pip python3-venv \
  autoconf automake libtool pkg-config zlib1g-dev libffi-dev libssl-dev \
  cmake ninja-build build-essential ccache libltdl-dev libncurses-dev \
  wget ca-certificates rsync >>"${LOG}" 2>&1

# Snapshot toolchain *before* this buildozer run.
"${VENV}/bin/python3" snapshot_toolchain.py | tee "${WORK}/toolchain_before.json"
find /root/.buildozer -type f -printf '%s %p\n' 2>/dev/null | sort -k2 > "${WORK}/files_before.txt" || true

echo "=== pin hostpython Cython 0.29.37 ===" | tee -a "${LOG}"
python3 "${WORK}/pin_hostpython_cython.py" >>"${LOG}" 2>&1 || true

echo "=== buildozer android debug (no deploy) ===" | tee -a "${LOG}"
# buildozer looks up `cython` on PATH, not next to its own script.
export PATH="${VENV}/bin:${PATH}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
command -v cython >>"${LOG}" 2>&1
cython --version >>"${LOG}" 2>&1 || true
set +e
buildozer android debug >>"${LOG}" 2>&1
RC=$?
set -e
echo "=== buildozer exit ${RC} $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "${LOG}"

"${VENV}/bin/python3" snapshot_toolchain.py | tee "${WORK}/toolchain_after.json"
find /root/.buildozer -type f -printf '%s %p\n' 2>/dev/null | sort -k2 > "${WORK}/files_after.txt" || true

# Copy evidence back onto the repo tree (APK if any, manifests, logs).
DEST="${SRC}/artifacts"
mkdir -p "${DEST}"
cp -a "${LOG}" "${DEST}/build.log" || true
cp -a "${WORK}/toolchain_before.json" "${WORK}/toolchain_after.json" "${DEST}/" || true
if [[ -d "${WORK}/bin" ]]; then
  cp -a "${WORK}/bin/." "${DEST}/bin/" 2>/dev/null || mkdir -p "${DEST}/bin"
  cp -a "${WORK}/bin/." "${DEST}/bin/" || true
fi
# Generated merged manifest, if the dist exists.
find "${WORK}/.buildozer" -name AndroidManifest.xml 2>/dev/null | head -20 > "${DEST}/manifest_paths.txt" || true
while IFS= read -r m; do
  [[ -n "$m" ]] || continue
  rel="${m#${WORK}/.buildozer/}"
  mkdir -p "${DEST}/manifests/$(dirname "$rel")"
  cp -a "$m" "${DEST}/manifests/$rel" || true
done < "${DEST}/manifest_paths.txt"

echo "BUILD_EXIT=${RC}" | tee -a "${LOG}"
exit "${RC}"
