"""Compatibility entry point; implementation lives in app.acquisition."""
import importlib
import sys

_impl = importlib.import_module('app.acquisition.connectors.file_connector')
sys.modules[__name__] = _impl
