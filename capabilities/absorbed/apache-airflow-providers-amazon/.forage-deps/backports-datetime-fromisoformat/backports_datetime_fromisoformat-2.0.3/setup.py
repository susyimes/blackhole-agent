import os

from setuptools import setup, Extension

# We want to force all warnings to be considered errors. That way we get to catch potential issues during
# development and at PR review time.
# But since backports.datetime_fromisoformat is a source distribution, exotic compiler configurations can cause spurious warnings that
# would fail the installation. So we only want to treat warnings as errors during development.
if os.environ.get("STRICT_WARNINGS", "0") == "1":
    # We can't use `extra_compile_args`, since the cl.exe (Windows) and gcc compilers don't use the same flags.
    # Further, there is not an easy way to tell which compiler is being used.
    # Instead we rely on each compiler looking at their appropriate environment variable.

    # GCC/Clang
    try:
        _ = os.environ["CFLAGS"]
    except KeyError:
        os.environ["CFLAGS"] = ""
    os.environ["CFLAGS"] += " -Werror"

    # cl.exe
    try:
        _ = os.environ["_CL_"]
    except KeyError:
        os.environ["_CL_"] = ""
    os.environ["_CL_"] += " /WX"

setup(
    packages=["backports", "backports.datetime_fromisoformat"],

    ext_modules=[Extension("backports._datetime_fromisoformat", [
        os.path.join("backports", "datetime_fromisoformat", "module.c"),
        os.path.join("backports", "datetime_fromisoformat", "_datetimemodule.c"),
        os.path.join("backports", "datetime_fromisoformat", "timezone.c")
    ])],
)
