# $Id: local-parser.py 9026 2022-03-04 15:57:13Z milde $
# Authors: Engelbert Gruber <grubert@users.sourceforge.net>
#          Toshio Kuratomi <toshio@fedoraproject.org>
# Copyright: This module is put into the public domain.

"""
mini-reader to test get_reader_class with local reader
"""

from docutils import parsers


class Parser(parsers.Parser):

    supported = ('dummy',)
    """Formats this reader supports."""

    def parser(self, inputstring, document):
        self.setup_parse(inputstring, document)
        self.finish_parse()
