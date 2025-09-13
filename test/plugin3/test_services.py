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

from typing import Callable

from picard.ui.plugins_manager.services import InstallerService
from picard.ui.plugins_manager.strategies import InstallationStrategy


class DummyStrategy(InstallationStrategy):
    def __init__(self) -> None:
        self.last_input: str | None = None
        self.calls: int = 0

    def validate_input(self, input_data: str) -> bool:
        return bool(input_data)

    def install(self, input_data: str, progress: Callable[[str], None]) -> list[str]:
        self.calls += 1
        self.last_input = input_data
        progress("working")
        return ["plugin-a", "plugin-b"]


def test_installer_service_delegates_to_strategies() -> None:
    dummy_git = DummyStrategy()
    dummy_local = DummyStrategy()
    service = InstallerService(git_strategy=dummy_git, local_strategy=dummy_local)

    got_git = service.install_from_git("https://example.com/x/y", progress=lambda _m: None)
    got_local = service.install_from_local("/tmp/plugins", progress=lambda _m: None)

    assert got_git == ["plugin-a", "plugin-b"]
    assert got_local == ["plugin-a", "plugin-b"]
    assert dummy_git.calls == 1 and dummy_git.last_input == "https://example.com/x/y"
    assert dummy_local.calls == 1 and dummy_local.last_input == "/tmp/plugins"
