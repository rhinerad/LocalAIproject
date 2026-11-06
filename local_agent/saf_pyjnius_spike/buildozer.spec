[app]
title = SAF Spike
package.name = safspike
package.domain = local.equalshares

source.dir = .
source.include_exts = py
source.exclude_patterns = .buildozer/*,bin/*,__pycache__/*,*.md,*.sh,snapshot_toolchain.py,toolchain_*.json,files_*.txt,patch_p4a_*.py,diagnose_*.py,check_artifacts.py

version.regex = __version__ = ['"](.*)['"]
version.filename = %(source.dir)s/main.py

# Minimal p4a probe. Same API/NDK/p4a pin as the Sideband overlay.
# Local recipes pin CPython 3.11.5 (upstream p4a at this commit wants 3.14,
# which NDK r25b did not complete). Not the companion package.
requirements = python3,kivy==2.3.0,pyjnius,android,setuptools
p4a.local_recipes = recipes

p4a.branch = master
p4a.commit = 1fc0269438c365e07ea456793c300e3e18773939
# p4a.source_dir is injected by build_spike.sh into [app] (a patched p4a
# tree). Do not put it under [buildozer]; Buildozer will ignore it.

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 24
android.ndk = 25b
android.skip_update = False
android.accept_sdk_license = True
android.archs = arm64-v8a
android.release_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 0
build_dir = ./.buildozer
bin_dir = ./bin
