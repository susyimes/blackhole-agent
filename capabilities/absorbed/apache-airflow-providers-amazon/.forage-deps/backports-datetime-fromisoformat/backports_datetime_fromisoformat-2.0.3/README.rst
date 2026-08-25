================================
backports.datetime_fromisoformat
================================

.. image:: https://github.com/movermeyer/backports.datetime_fromisoformat/actions/workflows/test.yml/badge.svg
    :target: https://github.com/movermeyer/backports.datetime_fromisoformat/actions/workflows/test.yml

A backport of Python 3.11's ``datetime.fromisoformat`` methods to earlier versions of Python 3.
Tested against Python 3.6, 3.7, 3.8, 3.9, 3.10 and 3.11

Current Status
--------------

Development of ``backports.datetime_fromisoformat`` is "complete". Outside of potential minor bug fixes, do not expect new development here.

Version 2 changes
-----------------

In version 1, ``backports.datetime_fromisoformat`` was a backport of the Python 3.7 version of the ``fromisoformat`` methods.
This meant that it was limited in being able to parse only timestamps that were in the format produced by ``datetime.isoformat``.

As of version 2, ``backports.datetime_fromisoformat`` is a backport of the Python 3.11 version of the ``fromisoformat`` methods, which can parse (almost) the entire ISO 8601 specification.
There are no changes required when upgrading from v1 to v2. The parser is simply able to parse a wider portion of the ISO 8601 specification.

However, starting in version 2, ``backports.datetime_fromisoformat`` will apply its changes to Python < 3.11, whereas v1 only applied changes to Python < 3.7.
If you happened to be using ``backports.datetime_fromisoformat`` v1 on Python 3.7 through Python 3.10 and then upgrade to v2, it will patch the ``fromisoformat`` methods, whereas in v1 it did not.
The result is that the ``fromisoformat`` methods will suddenly be able to parse timestamps from a wider portion of the ISO 8601 specification.

Quick Start
-----------

**Installation:**

.. code:: bash

  pip install "backports-datetime-fromisoformat; python_version < '3.11'"

**Usage:**

.. code:: python

  >>> from datetime import date, datetime, time
  >>> from backports.datetime_fromisoformat import MonkeyPatch
  >>> MonkeyPatch.patch_fromisoformat()

  >>> datetime.fromisoformat("2014-01-09T21:48:00-05:30")
  datetime.datetime(2014, 1, 9, 21, 48, tzinfo=-05:30)

  >>> date.fromisoformat("2014-01-09")
  datetime.date(2014, 1, 9)

  >>> time.fromisoformat("21:48:00-05:30")
  datetime.time(21, 48, tzinfo=-05:30)

Explanation
-----------
In Python 3.7, `datetime.fromisoformat`_ was added. It is the inverse of `datetime.isoformat`_.
Similar methods were added to the ``date`` and ``time`` types as well.

In Python 3.11, `datetime.fromisoformat`_ was extended to cover (almost) all of the ISO 8601 specification, making it generally useful.

For those who need to support earlier versions of Python, a backport of these methods was needed.

.. _`datetime.fromisoformat`: https://docs.python.org/3/library/datetime.html#datetime.datetime.fromisoformat

.. _`datetime.isoformat`: https://docs.python.org/3/library/datetime.html#datetime.date.isoformat

``backports.datetime_fromisoformat`` is a C implementation of ``fromisoformat`` based on the upstream cPython 3.11 code.
For timezone objects, it uses a custom ``timezone`` C implementation (originally from `Pendulum`_).

.. _`Pendulum`: https://pendulum.eustace.io/

Usage in Python 3.11+
---------------------

NOTE: in Python 3.11 and later, compatible versions of ``fromisoformat`` methods exist in the stdlib, and installing this package has NO EFFECT.

Goal / Project Scope
--------------------

The purpose of this project is to provide a perfect backport of the ``fromisoformat`` methods to earlier versions of Python, while still providing comparable performance.
