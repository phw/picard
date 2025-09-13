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

import pytest

from picard.ui.plugins_manager.validation import UrlValidator


@pytest.fixture
def validator() -> UrlValidator:
    return UrlValidator()


@pytest.mark.parametrize(
    ("url", "is_valid"),
    [
        ("https://github.com/user/repo", True),
        ("https://github.com/user/repo.git", True),
        ("https://gitlab.com/user/repo", True),
        ("https://bitbucket.org/user/repo", True),
        ("https://git.sr.ht/~user/repo", True),
        ("https://github.com/user/repo/", True),
        ("https://github.com/user/repo.git/", True),
        ("http://github.com/user/repo", True),
        ("https://github.com:443/user/repo", True),
        ("https://user@github.com/user/repo", True),
        ("", False),
        ("not-a-url", False),
        ("ftp://github.com/user/repo", False),
        ("https://github.com", False),
        ("https://github.com/user", False),
        ("https://github.com/user/", False),
        ("file:///path/to/repo", False),
        ("git@github.com:user/repo.git", False),
        ("https://github.com/user/repo/tree/branch", False),
        ("https://github.com/user/repo/issues", False),
    ],
)
def test_url_validator_matrix(validator: UrlValidator, url: str, is_valid: bool) -> None:
    assert validator.is_valid_git_url(url) is is_valid
