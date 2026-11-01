"""Compatibility entry point; implementation lives in app.acquisition."""
import importlib
import sys

_impl = importlib.import_module('app.acquisition.services.acquisition_service')
sys.modules[__name__] = _impl
