# This is a namespace package so that `backports.datetime_fromisoformat` can integrate 
# nicely with the other `backports` modules.
# See https://packaging.python.org/guides/packaging-namespace-packages/#pkgutil-style-namespace-packages

__path__ = __import__('pkgutil').extend_path(__path__, __name__)