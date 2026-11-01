"""Compatibility entry point; implementation lives in app.acquisition."""
import importlib
import sys

_impl = importlib.import_module('app.acquisition.seed')
if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
