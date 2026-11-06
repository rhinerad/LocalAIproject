# 2026-08-29 — PowerInfer native toolchain gate

## What changed

- Cloned the upstream PowerInfer source into `external/PowerInfer` and prepared
  its isolated Python environment. Upstream's two bundled local packages are
  installed explicitly because modern pip rejects the upstream bare `./...`
  requirement lines.
- Verified the environment imports the PowerInfer Python packages and CUDA
  12.8 PyTorch reports CUDA available. This was an availability probe only;
  it did not load a model or execute inference.
- Hardened `tools/powerinfer/run_pipeline.ps1`: it now requires a Visual Studio
  2022 (17.x) C++ instance and its matching `Visual Studio 17 2022` generator.
  It preflights that requirement before cloning or installing Python packages,
  and will not auto-select Visual Studio 2026 merely because that is newest.
- Updated the PowerInfer README to use the supported `relu-llama-7b` PoC name
  rather than the retired ProSparse example, and to state the VS 2022 host
  compiler requirement.
- Added an offline regression assertion that the runner continues to require
  the CUDA-supported VS 2022 generator rather than silently selecting VS 2026.
- Passed CMake the verified CUDA runtime-library path explicitly; this avoids a
  CMake Windows host-architecture discovery edge case that otherwise misses
  `lib\\x64\\cudart.lib` even though CUDA itself is installed.
- Made the native toolchain probe find `nvcc.exe` from the standard installed
  CUDA roots when its `bin` folder is not already on the invoking shell's PATH.
- Corrected the runner's VS-bundled CMake resolution to retain its file path,
  rather than treating a file-system object as a command-discovery object.
- Scoped new native output to `external/PowerInfer/build-vs2022`; the runner
  preserves the failed VS 2026 CMake cache rather than deleting or reusing it.
- Updated the matching control-plane and runner documentation to use that
  compiler-scoped binary location.

## Evidence and current blocker

- The installed toolkit is CUDA 12.8 and CMake successfully locates its
  headers, runtime, and cuBLAS libraries when given the runtime library path.
- The workstation has Visual Studio Community 2026 (18.x) with C++ tools, but
  no VS 2022 (17.x) instance. CUDA 12.8 rejects VS 2026; with the documented
  override, `cudafe++` terminates with an access violation during CMake's CUDA
  compiler-identification step. This is a host-compiler compatibility failure,
  not a missing CUDA library or a PowerInfer/model failure.
- No PowerInfer binary was produced. No sparse model, predictor, activation
  asset, model download, PowerInfer server, render, or GPU inference was
  started.

## Next action

Install Visual Studio 2022 Build Tools or Community with **Desktop development
with C++** side-by-side. Then rerun only the controlled native setup/build;
the accepted-model registry, GPU-gateway approval, and measured acceptance
gates still block any endpoint activation.

The same explicit prerequisite is recorded as an unchecked PowerInfer task in
`TODO.md` so later continuations do not retry the incompatible VS 2026 path.
