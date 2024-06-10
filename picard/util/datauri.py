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
from collections import namedtuple
from urllib.parse import unquote


DataURI = namedtuple('DataURI', 'scheme mediatype encoding data')


class ParseError(Exception):
    pass


def parse(uri: str) -> DataURI:
    if not uri.startswith('data:'):
        raise ParseError('Expected URI to start with "data:"')
    mediatype, data = uri[5:].split(',', 1)
    encoding = 'urlencoded'
    if mediatype.endswith(';base64'):
        mediatype = mediatype[:-7]
        encoding = 'base64'
    return DataURI('data', mediatype, encoding, _decode_data(encoding, data))


def _decode_data(encoding, data):
    if encoding == 'base64':
        return b64decode(data)
    else:
        return unquote(data)
