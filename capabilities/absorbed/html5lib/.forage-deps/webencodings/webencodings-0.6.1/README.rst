webencodings is a Python implementation of the `WHATWG Encoding standard
<http://encoding.spec.whatwg.org/>`_.

In order to be compatible with legacy web content when interpreting something like
``Content-Type: text/html; charset=latin1``, tools need to use a particular set of
aliases for encoding labels as well as some overriding rules. For example, ``US-ASCII``
and ``iso-8859-1`` on the web are actually aliases for ``windows-1252``, and an UTF-8 or
UTF-16 BOM takes precedence over any other encoding declaration. The Encoding standard
defines all such details so that implementations do not have to reverse-engineer each
other.

This module has encoding labels and BOM detection, but the actual implementation for
encoders and decoders is Python’s.

* Free software: BSD license
* For Python 3.10+, tested on CPython and PyPy
* Documentation: https://doc.courtbouillon.org/webencodings
* Changelog: https://github.com/CourtBouillon/webencodings/releases
* Code, issues, tests: https://github.com/CourtBouillon/webencodings
* Code of conduct: https://www.courtbouillon.org/code-of-conduct
* Professional support: https://www.courtbouillon.org
* Donation: https://opencollective.com/courtbouillon

This module is a friendly fork of webencodings, written and maintained by Simon Sapin
and Sam Sneddon.

Copyrights are retained by their contributors, no copyright assignment is required to
contribute to webencodings. Unless explicitly stated otherwise, any contribution
intentionally submitted for inclusion is licensed under the BSD 3-clause license,
without any additional terms or conditions. For full authorship information, see the
version control history.
