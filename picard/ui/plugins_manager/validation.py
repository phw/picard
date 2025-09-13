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

import re
from urllib.parse import urlparse


class UrlValidator:
    """Validate plugin source URLs.

    Methods
    -------
    is_valid_git_url(url)
        Return whether the input is a valid HTTPS git repository URL.
    """

    _git_url_pattern = re.compile(r'^https?://(?:[^@/]+@)?(?:[^:/]+)(?::\d+)?/[^/]+/[^/]+(?:\.git)?/?$')

    def is_valid_git_url(self, url: str) -> bool:
        """Return whether the input is a valid HTTPS git repository URL.

        Parameters
        ----------
        url
            URL to validate.
        """
        if not url:
            return False
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
        except (ValueError, TypeError):
            return False
        return bool(self._git_url_pattern.match(url))
