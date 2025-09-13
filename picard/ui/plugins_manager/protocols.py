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

from typing import Callable, Protocol

from PyQt6 import QtWidgets  # type: ignore[import-not-found]


class InstallationSource(Protocol):
    """Abstraction for an installation source tab."""

    def widget(self) -> QtWidgets.QWidget:
        """Return the underlying widget for embedding in a tab."""

    def is_ready(self) -> bool:
        """Return whether the source has valid inputs to enable Install."""

    def reset(self) -> None:
        """Reset inputs to initial state."""

    def on_change(self, cb: Callable[[], None]) -> None:
        """Register a callback invoked when readiness may have changed."""

    def collect_inputs(self) -> dict:
        """Return normalized inputs for the coordinator to act upon."""


class PluginManagerProtocol(Protocol):
    """Minimal protocol for plugin management used by the dialog."""

    def get_enabled_plugins(self) -> list[str]:
        """Return list of enabled plugin slugs."""

    def enable_plugin(self, name: str) -> None:
        """Enable plugin by slug."""

    def disable_plugin(self, name: str) -> None:
        """Disable plugin by slug."""
