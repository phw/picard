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

from picard.plugin3.installer import PluginInstallationError

from picard.ui.plugins_manager.protocols import InstallationSource
from picard.ui.plugins_manager.services import InstallerService


class InstallCoordinator:
    """Coordinate installation for the current source using InstallerService."""

    def __init__(self, service: InstallerService):
        self._service = service
        self._source: InstallationSource | None = None

    def set_source(self, source: InstallationSource | None) -> None:
        self._source = source

    def is_ready(self) -> bool:
        return bool(self._source and self._source.is_ready())

    def install(self, progress: Callable[[str], None]) -> tuple[list[str], int]:
        if not self._source:
            return ([], 0)
        inputs = self._source.collect_inputs()
        error_count = 0
        if "urls" in inputs:
            installed: list[str] = []
            seen: set[str] = set()
            for url in inputs["urls"]:
                if url in seen:
                    continue
                seen.add(url)
                try:
                    installed += self._service.install_from_git(url, progress=progress)
                except PluginInstallationError:
                    error_count += 1
            return (installed, error_count)
        if "directory" in inputs:
            try:
                installed = self._service.install_from_local(inputs["directory"], progress=progress)
                return (installed, 0)
            except PluginInstallationError:
                return ([], 1)
        return ([], 0)
