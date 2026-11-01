"""Compatibility entry point; implementation lives in app.acquisition."""
import importlib
import sys

_impl = importlib.import_module('app.acquisition.connectors.directory_connector')
sys.modules[__name__] = _impl
