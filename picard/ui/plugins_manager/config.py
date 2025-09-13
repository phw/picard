# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2025 Philipp Wolfer
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


class DialogConfig:
    """Configuration for the plugin installation dialog.

    Attributes
    ----------
    default_width
        Initial dialog width in pixels.
    default_height
        Initial dialog height in pixels.
    description_preview_chars
        Maximum characters for description preview.
    max_urls
        Maximum number of URL input rows.
    """

    DEFAULT_WIDTH: int = 800
    DEFAULT_HEIGHT: int = 400
    DESCRIPTION_MAX_CHARS: int = 100
    MAX_URLS: int = 5
