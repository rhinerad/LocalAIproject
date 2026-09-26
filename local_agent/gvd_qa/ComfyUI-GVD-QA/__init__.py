"""Reviewed GVD QA adapter package. Do not drop into Rockernow without promotion."""
from pathlib import Path
import importlib.util

_here = Path(__file__).resolve().parent
_compat = _here / "transformers_compat.py"
if not _compat.is_file():
    _compat = _here.parent / "transformers_compat.py"
if _compat.is_file():
    _cspec = importlib.util.spec_from_file_location("gvd_qa_transformers_compat", _compat)
    _cmod = importlib.util.module_from_spec(_cspec)
    assert _cspec.loader is not None
    _cspec.loader.exec_module(_cmod)
    _cmod.patch_transformers_for_imagereward()

_ADAPTERS = _here / "comfy_adapters.py"
if not _ADAPTERS.is_file():
    _ADAPTERS = _here.parent / "comfy_adapters.py"
_spec = importlib.util.spec_from_file_location("gvd_qa_comfy_adapters", _ADAPTERS)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

NODE_CLASS_MAPPINGS = _mod.NODE_CLASS_MAPPINGS
NODE_DISPLAY_NAME_MAPPINGS = {name: name for name in NODE_CLASS_MAPPINGS}
WEB_DIRECTORY = None
