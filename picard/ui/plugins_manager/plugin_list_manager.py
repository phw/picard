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

from contextlib import suppress
from pathlib import Path
import shutil

from PyQt6 import QtCore, QtWidgets  # type: ignore[import-not-found]

from picard import log
from picard.const.appdirs import plugin_folder

from picard.ui.plugins_manager.list_components import (
    SLUG_ROLE,
    PluginListModel,
    get_installed_plugins_with_labels,
)
from picard.ui.plugins_manager.protocols import PluginManagerProtocol


class PluginListManager:
    """Manage the installed plugins list view, model, and actions.

    Parameters
    ----------
    view
        The `QListView` showing installed plugins.
    model
        The `PluginListModel` backing the view.
    plugin_manager
        Object implementing `PluginManagerProtocol` for enable/disable.
    """

    def __init__(self, view: QtWidgets.QListView, model: PluginListModel, plugin_manager: PluginManagerProtocol):
        self._view = view
        self._model = model
        self._pm = plugin_manager
        self._disabled: set[str] = set()

    def refresh(self, preserve_selection: bool = True) -> None:
        """Reload installed plugins and update disabled state."""
        previously_selected_slug = self.selected_slug() if preserve_selection else None

        items = get_installed_plugins_with_labels()
        self._model.set_plugins(items)
        enabled = set()
        with suppress(AttributeError):
            enabled = set(self._pm.get_enabled_plugins())
        self._disabled = {slug for (slug, _label) in items} - enabled
        self._model.set_disabled(self._disabled)

        if previously_selected_slug is not None and self._view.selectionModel():
            selection_model = self._view.selectionModel()
            for row in range(self._model.rowCount()):
                index = self._model.index(row, 0)
                slug = self._model.data(index, SLUG_ROLE)
                if slug == previously_selected_slug:
                    flags = (
                        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                        | QtCore.QItemSelectionModel.SelectionFlag.Current
                    )
                    selection_model.setCurrentIndex(index, flags)
                    self._view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
                    break

    def selected_slug(self) -> str | None:
        """Return the currently selected plugin slug, if any."""
        indexes = self._view.selectedIndexes()
        if not indexes:
            return None
        return self._model.data(indexes[0], SLUG_ROLE)

    def update_action_buttons(
        self, toggle_button: QtWidgets.QPushButton, uninstall_button: QtWidgets.QPushButton
    ) -> None:
        """Enable/disable and set labels for action buttons based on selection state."""
        name = self.selected_slug()
        if not name:
            toggle_button.setEnabled(False)
            toggle_button.setText("Enable")
            uninstall_button.setEnabled(False)
            return
        is_disabled = name in self._disabled
        toggle_button.setEnabled(True)
        toggle_button.setText("Enable" if is_disabled else "Disable")
        uninstall_button.setEnabled(True)

    def toggle_selected(self) -> None:
        """Toggle enable/disable for the selected plugin."""
        name = self.selected_slug()
        if not name:
            return
        try:
            if name in self._disabled:
                self._pm.enable_plugin(name)
            else:
                self._pm.disable_plugin(name)
        except (ImportError, OSError, AttributeError, TypeError) as e:
            log.warning("Failed to toggle plugin %s: %s", name, e)
        self.refresh(preserve_selection=True)

    def uninstall_selected(self) -> None:
        """Uninstall the selected plugin by removing its directory and disabling it."""
        name = self.selected_slug()
        if not name:
            return
        with suppress(ImportError, OSError, AttributeError, TypeError):
            self._pm.disable_plugin(name)
        try:
            target_dir = Path(plugin_folder()) / name
            if target_dir.exists():
                shutil.rmtree(target_dir)
        except OSError as e:
            log.warning("Failed to uninstall plugin %s: %s", name, e)
        self._disabled.discard(name)
        self.refresh(preserve_selection=False)

    def enable_by_name(self, plugin_name: str) -> None:
        """Enable a plugin by slug via the plugin manager, then refresh."""
        try:
            self._pm.enable_plugin(plugin_name)
        except (ImportError, OSError, AttributeError, TypeError) as e:
            log.warning("Failed to enable plugin %s: %s", plugin_name, e)
        self.refresh(preserve_selection=True)
