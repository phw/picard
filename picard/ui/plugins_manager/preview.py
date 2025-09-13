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

"""Repository preview utilities for plugin manifests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Callable

from picard.plugin3.installer import (
    GitRepositoryFetcher,
    ManifestValidationError,
    PluginDiscovery,
    PluginValidator,
)
from picard.plugin3.manifest import PluginManifest


ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class GitRepositoryPreviewer:
    """Preview a git repository and extract plugin manifest metadata.

    Methods
    -------
    analyze(url, progress)
        Clone the repository into a temporary directory, discover plugins,
        validate them, and return tuples of ``(name, path, manifest)`` plus
        a list of invalid error messages.
    """

    fetcher: GitRepositoryFetcher = GitRepositoryFetcher()
    discovery: PluginDiscovery = PluginDiscovery()
    validator: PluginValidator = PluginValidator()

    def analyze(
        self, url: str, progress: ProgressCallback | None = None
    ) -> tuple[list[tuple[str, Path, PluginManifest]], list[str]]:
        """Analyze repository and return valid entries with manifests.

        Parameters
        ----------
        url
            Repository URL.
        progress
            Optional progress callback.

        Returns
        -------
        list[tuple[str, Path, PluginManifest]], list[str]
            Tuples of valid plugin entries and a list of invalid error strings.

        Raises
        ------
        RepositoryCloneError
            If cloning fails.
        ManifestValidationError
            If no plugins are found.
        PluginInstallationError
            For other installation-related errors.
        """

        def notify(message: str) -> None:
            if progress:
                progress(message)

        valid: list[tuple[str, Path, PluginManifest]] = []
        invalid_errors: list[str] = []

        with tempfile.TemporaryDirectory(prefix="picard-plugin-preview-") as tmp:
            tmp_path = Path(tmp)
            repo_path = tmp_path.joinpath("repo")

            notify(f"Cloning {url}...")
            local_repo = self.fetcher.fetch(url, repo_path)

            notify("Scanning repository for plugins...")
            candidates = self.discovery.discover(local_repo)
            if not candidates:
                raise ManifestValidationError("No plugins found in repository")

            notify("Validating plugin manifests...")
            for c in candidates:
                try:
                    name = self.validator.validate(c)
                    with open(c / "MANIFEST.toml", 'rb') as fp:
                        manifest = PluginManifest(c.name, fp)
                    valid.append((name, c, manifest))
                except (ManifestValidationError, OSError) as ex:
                    invalid_errors.append(f"{c.name}: {ex}")

        return (valid, invalid_errors)
