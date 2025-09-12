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

from abc import ABC, abstractmethod
from contextlib import suppress
from pathlib import Path
from typing import Callable

from picard.plugin3.installer import (
    ManifestValidationError,
    PluginCopier,
    PluginDiscovery,
    PluginInstallationError,
    PluginInstallationService,
    PluginValidator,
)


ProgressCallback = Callable[[str], None]


class InstallationStrategy(ABC):
    """Strategy for installing plugins from a given source."""

    @abstractmethod
    def validate_input(self, input_data: str) -> bool:
        """Return whether the input is valid for this strategy.

        Parameters
        ----------
        input_data
            Strategy-specific input string, e.g. URL or path.
        """

    @abstractmethod
    def install(self, input_data: str, progress: ProgressCallback) -> list[str]:
        """Install plugins and return installed plugin names.

        Parameters
        ----------
        input_data
            Strategy-specific input data.
        progress
            Callback receiving progress messages.
        """


class GitInstallationStrategy(InstallationStrategy):
    """Install from a git repository URL."""

    def __init__(self, service: PluginInstallationService | None = None):
        self._service = service or PluginInstallationService()

    def validate_input(self, input_data: str) -> bool:
        return bool(input_data)

    def install(self, input_data: str, progress: ProgressCallback) -> list[str]:
        try:
            return self._service.install_from_git(input_data, progress=progress)
        except PluginInstallationError as ex:
            raise ex


class LocalInstallationStrategy(InstallationStrategy):
    """Install from a local directory containing one or more plugins."""

    def __init__(self, copier: PluginCopier | None = None):
        self._copier = copier or PluginCopier()

    def validate_input(self, input_data: str) -> bool:
        return bool(input_data)

    def install(self, input_data: str, progress: ProgressCallback) -> list[str]:
        path = Path(input_data)
        progress("Scanning directory for plugins...")

        discovery = PluginDiscovery()
        validator = PluginValidator()

        if (path / "__init__.py").exists() and (path / "MANIFEST.toml").exists():
            candidates = [path]
        else:
            candidates = discovery.discover(path)

        if not candidates:
            raise ManifestValidationError("No plugins found in directory")

        progress("Validating plugin manifests...")
        validated: list[tuple[str, Path]] = []
        for candidate in candidates:
            name = validator.validate(candidate)
            validated.append((name, candidate))

        progress("Installing plugins...")
        from picard.plugin3.installer import PluginCopyPlan

        copy_plans = [
            PluginCopyPlan(source=src, target=self._copier.plugins_root.joinpath(name)) for (name, src) in validated
        ]
        self._copier.copy(copy_plans)

        for name, _src in validated:
            with suppress(OSError):
                (self._copier.plugins_root / name / ".installed").touch(exist_ok=True)

        return [name for (name, _src) in validated]
