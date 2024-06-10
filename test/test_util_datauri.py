# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2024 Philipp Wolfer
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

from base64 import b64decode

from test.picardtestcase import PicardTestCase

from picard.util import datauri


class DataURITest(PicardTestCase):
    """Parses a data URI as defined in RFC 2397.

    See https://datatracker.ietf.org/doc/html/rfc2397
    """
    def test_parse_base64(self):
        pngdata = 'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAXUlEQVQY073MvQ2CUADE8R90tOzgFkzgMg7gLs7BCDYmhD0sTV7F2Vi8EF5nuOpyH3/+rW4fhMvPDh3r4Stcwxxe4dbEh3co4ROedddXowmlyrYwtoj3sIRHc3S+vgySGhd7StmKAAAAAElFTkSuQmCC'
        uri = 'data:image/png;base64,' + pngdata
        result = datauri.parse(uri)
        self.assertEqual('data', result.scheme)
        self.assertEqual('image/png', result.mediatype)
        self.assertEqual('base64', result.encoding)
        self.assertEqual(b64decode(pngdata), result.data)

    def test_parse_urlencoded(self):
        uri = 'data:text/plain,some%20data'
        result = datauri.parse(uri)
        self.assertEqual('data', result.scheme)
        self.assertEqual('text/plain', result.mediatype)
        self.assertEqual('urlencoded', result.encoding)
        self.assertEqual('some data', result.data)

    def test_parse_invalid(self):
        with self.assertRaises(datauri.ParseError):
            datauri.parse("text/plain,some%20data")
