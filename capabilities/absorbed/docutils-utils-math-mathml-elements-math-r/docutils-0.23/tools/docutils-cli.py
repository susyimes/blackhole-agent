#!/usr/bin/env python3
# :Copyright: © 2022 Günter Milde.
# :License: Released under the terms of the `2-Clause BSD license`_, in short:
#
#    Copying and distribution of this file, with or without modification,
#    are permitted in any medium without royalty provided the copyright
#    notice and this notice are preserved.
#    This file is offered as-is, without any warranty.
#
# .. _2-Clause BSD license: https://opensource.org/licenses/BSD-2-Clause
#
# Revision: $Revision: 9061 $
# Date: $Date: 2022-05-30 18:54:46 +0200 (Mo, 30. Mai 2022) $

"""Generic command line interface for the `docutils` package.

Deprecated:
Call `docutils` (generated in the binary PATH during package installation)
or `python3 -m docutils` to get the generic Docutils CLI.
"""

from docutils import __main__

__main__.main()
