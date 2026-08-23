# $Id: local-reader.py 9037 2022-03-05 23:31:10Z milde $
# Authors: Engelbert Gruber <grubert@users.sourceforge.net>
#          Toshio Kuratomi <toshio@fedoraproject.org>
# Copyright: This module is put into the public domain.

"""
mini-reader to test get_reader_class with local reader
"""

from docutils import readers


class Reader(readers.Reader):

    supported = ('dummy',)
    """Formats this reader supports."""

    document = None
    """A document tree."""
