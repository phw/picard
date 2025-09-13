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

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from typing import Callable, Iterable

from picard import api_versions_tuple, log
from picard.const.appdirs import plugin_folder
from picard.plugin3.manifest import PluginManifest
from picard.version import Version


class PluginInstallationError(Exception):
    """Base error for plugin installation failures."""


class RepositoryCloneError(PluginInstallationError):
    """Raised when cloning or fetching a repository fails."""


class ManifestValidationError(PluginInstallationError):
    """Raised when a plugin directory has an invalid or missing MANIFEST.toml."""


class PluginCopyError(PluginInstallationError):
    """Raised when copying plugin files into the target directory fails."""


ProgressCallback = Callable[[str], None]


class RepositoryFetcher:
    """Abstract repository fetcher.

    Subclasses should implement `fetch` and return the local repository path.
    """

    def fetch(self, repo_url: str, dest_dir: Path) -> Path:
        raise NotImplementedError


class GitRepositoryFetcher(RepositoryFetcher):
    """Fetch a repository using pygit2.

    Notes
    -----
    Requires `pygit2` to be installed. If unavailable, raises
    `RepositoryCloneError` with a helpful message.
    """

    def fetch(self, repo_url: str, dest_dir: Path) -> Path:
        try:
            import pygit2  # type: ignore[import-not-found]  # Local import to avoid hard dependency at import time
        except ImportError as exc:
            raise RepositoryCloneError("pygit2 is required to install plugins from git repositories") from exc

        try:
            # Ensure parent exists and target does not (pygit2 expects not existing)
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            pygit2.clone_repository(str(repo_url), str(dest_dir))
        except (pygit2.GitError, OSError) as exc:
            raise RepositoryCloneError(f"Failed cloning {repo_url}: {exc}") from exc
        else:
            log.debug("Cloned repository %s to %s", repo_url, dest_dir)
            return dest_dir


class PluginDiscovery:
    """Discover plugin packages inside a repository checkout.

    A plugin package is defined as a directory containing both
    `__init__.py` and `MANIFEST.toml`.
    """

    def discover(self, repo_root: Path) -> list[Path]:
        candidates: list[Path] = []
        for entry in repo_root.rglob("*"):
            if entry.is_dir():
                init_file = entry.joinpath("__init__.py")
                manifest_file = entry.joinpath("MANIFEST.toml")
                if init_file.is_file() and manifest_file.is_file():
                    candidates.append(entry)
        return candidates


class PluginValidator:
    """Validate plugin directories and compatibility."""

    def validate(self, plugin_dir: Path) -> str:
        """Validate a single plugin directory.

        Parameters
        ----------
        plugin_dir
            Directory path of the plugin candidate.

        Returns
        -------
        str
            The plugin name (directory name) if valid.

        Raises
        ------
        ManifestValidationError
            If the manifest is missing or invalid, or API versions are incompatible.
        """
        manifest_path = plugin_dir.joinpath("MANIFEST.toml")
        init_file = plugin_dir.joinpath("__init__.py")
        if not manifest_path.is_file() or not init_file.is_file():
            raise ManifestValidationError(f"Not a plugin package: {plugin_dir}")

        # Read manifest
        try:
            with open(manifest_path, "rb") as fp:
                manifest = PluginManifest(plugin_dir.name, fp)
        except OSError as exc:
            raise ManifestValidationError(f"Failed reading manifest: {manifest_path}") from exc

        # Check API compatibility
        if not self._is_compatible(manifest.api_versions):
            raise ManifestValidationError(f"Plugin {plugin_dir.name} is not compatible with this Picard version")
        return plugin_dir.name

    def _is_compatible(self, api_versions: tuple[Version, ...]) -> bool:
        if not api_versions:
            return False
        return bool(set(api_versions) & set(api_versions_tuple))


@dataclass
class PluginCopyPlan:
    source: Path
    target: Path


class PluginCopier:
    """Copy validated plugins into the user's plugins directory."""

    def __init__(self, plugins_root: Path | None = None) -> None:
        self._plugins_root = Path(plugins_root) if plugins_root else Path(plugin_folder())
        self._plugins_root.mkdir(parents=True, exist_ok=True)

    @property
    def plugins_root(self) -> Path:
        return self._plugins_root

    def copy(self, plans: Iterable[PluginCopyPlan]) -> None:
        for plan in plans:
            self._copy_one(plan)

    def _copy_one(self, plan: PluginCopyPlan) -> None:
        try:
            # Replace existing installation atomically when possible
            if plan.target.exists():
                shutil.rmtree(plan.target)
            shutil.copytree(
                plan.source,
                plan.target,
                dirs_exist_ok=False,
                symlinks=True,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    ".git",
                    ".gitignore",
                    "*.egg-info",
                    ".pytest_cache",
                    ".coverage",
                ),
            )
            log.debug("Installed plugin from %s to %s", plan.source, plan.target)
        except (OSError, shutil.Error) as exc:
            raise PluginCopyError(f"Failed installing plugin to {plan.target}: {exc}") from exc


class PluginInstallationService:
    """High-level service coordinating plugin installation from repositories.

    Adheres to SRP and SOC by delegating fetching, discovery, validation
    and copying to dedicated collaborators injected via the constructor.
    """

    def __init__(
        self,
        fetcher: RepositoryFetcher | None = None,
        discovery: PluginDiscovery | None = None,
        validator: PluginValidator | None = None,
        copier: PluginCopier | None = None,
    ) -> None:
        self._fetcher = fetcher or GitRepositoryFetcher()
        self._discovery = discovery or PluginDiscovery()
        self._validator = validator or PluginValidator()
        self._copier = copier or PluginCopier()

    def install_from_git(self, repo_url: str, progress: ProgressCallback | None = None) -> list[str]:
        """Install all plugins found in the given git repository URL.

        Parameters
        ----------
        repo_url
            The URL of the git repository to clone.
        progress
            Optional callback for progress messages.

        Returns
        -------
        list[str]
            Names of plugins installed.

        Raises
        ------
        PluginInstallationError
            If any step of the installation fails.
        """

        def notify(message: str) -> None:
            if progress:
                progress(message)

        installed: list[str] = []
        with tempfile.TemporaryDirectory(prefix="picard-plugin-") as tmp:
            tmp_path = Path(tmp)
            repo_path = tmp_path.joinpath("repo")

            notify(f"Cloning {repo_url}...")
            local_repo = self._fetcher.fetch(repo_url, repo_path)

            notify("Scanning repository for plugins...")
            candidates = self._discovery.discover(local_repo)
            if not candidates:
                raise ManifestValidationError("No plugins found in repository")

            notify("Validating plugin manifests...")
            validated: list[tuple[str, Path]] = []
            for candidate in candidates:
                name = self._validator.validate(candidate)
                validated.append((name, candidate))

            notify("Installing plugins...")
            plans = [
                PluginCopyPlan(source=src, target=self._copier.plugins_root.joinpath(name)) for (name, src) in validated
            ]
            self._copier.copy(plans)
            installed = [name for (name, _src) in validated]

        # Best effort: ignore failures while cleaning tmp dirs
        with suppress(OSError):
            for name in installed:
                # Touch an installation marker for future use
                Path(self._copier.plugins_root, name, ".installed").touch(exist_ok=True)

        return installed
