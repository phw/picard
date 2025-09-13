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

from pathlib import Path
from typing import Callable

from PyQt6 import QtCore, QtWidgets  # type: ignore[import-not-found]

from picard.i18n import gettext as _
from picard.plugin3.installer import (
    ManifestValidationError,
    PluginDiscovery,
    PluginValidator,
)

from picard.ui.plugins_manager.config import DialogConfig
from picard.ui.plugins_manager.manifest_info import build_manifest_info_html
from picard.ui.plugins_manager.protocols import InstallationSource
from picard.ui.plugins_manager.widgets import FeedbackWidget
from picard.ui.util import FileDialog


class LocalInstallTab(InstallationSource):
    """Installation source for local directory installs.

    This widget owns the directory input, browse button, local feedback container,
    and plugin info group. Validation and preview can be handled externally
    (e.g., by the dialog) while this class exposes minimal readiness and inputs.
    """

    def __init__(self, parent=None):
        self._container = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(self._container)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        title_label = QtWidgets.QLabel(_("Install Plugin from Local Directory"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        desc_label = QtWidgets.QLabel(
            _(
                "Select a local directory containing a Picard plugin or a repository with "
                "one or more plugin directories. Each plugin directory must contain "
                "a MANIFEST.toml file and follow the plugin package structure."
            )
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)

        dir_layout = QtWidgets.QHBoxLayout()
        dir_label = QtWidgets.QLabel(_("Plugin Directory:"))
        dir_label.setMinimumWidth(120)
        dir_layout.addWidget(dir_label)

        self.local_dir_input = QtWidgets.QLineEdit()
        self.local_dir_input.setPlaceholderText(_("Select a directory containing a plugin"))
        dir_layout.addWidget(self.local_dir_input, stretch=1)

        self.browse_button = QtWidgets.QPushButton(_("Browse..."))
        dir_layout.addWidget(self.browse_button)
        layout.addLayout(dir_layout)

        self.local_feedback_container = QtWidgets.QFrame()
        self.local_feedback_container.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        local_feedback_layout = QtWidgets.QVBoxLayout(self.local_feedback_container)
        local_feedback_layout.setContentsMargins(0, 0, 0, 0)
        local_feedback_layout.setSpacing(0)

        self.local_feedback = FeedbackWidget()
        local_feedback_layout.addWidget(self.local_feedback)
        layout.addWidget(self.local_feedback_container)

        self.plugin_info_group = QtWidgets.QGroupBox(_("Plugin Information"))
        plugin_info_layout = QtWidgets.QVBoxLayout(self.plugin_info_group)
        self.plugin_info_text = QtWidgets.QTextEdit()
        self.plugin_info_text.setReadOnly(True)
        self.plugin_info_text.setMaximumHeight(120)
        self.plugin_info_text.setPlaceholderText(
            _("Plugin information will appear here when a valid directory is selected")
        )
        plugin_info_layout.addWidget(self.plugin_info_text)
        layout.addWidget(self.plugin_info_group)

        layout.addStretch(1)

        self._on_change: Callable[[], None] | None = None
        self._ready: bool = False
        self._discovered_local_plugins: list[Path] = []

        # Wire events: validate on change, open browser on click
        self.local_dir_input.textChanged.connect(lambda _t: self._validate_local_directory())
        self.browse_button.clicked.connect(self._browse_local_directory)

    def widget(self) -> QtWidgets.QWidget:
        return self._container

    def is_ready(self) -> bool:
        return self._ready

    def set_ready(self, ready: bool) -> None:
        self._ready = ready

    def reset(self) -> None:
        self.local_dir_input.clear()
        self._discovered_local_plugins = []
        self.local_feedback.clear_and_hide()
        self.local_feedback_container.hide()
        self.plugin_info_text.clear()
        self._set_ready(False)

    def on_change(self, cb: Callable[[], None]) -> None:
        self._on_change = cb

    def _emit_change(self) -> None:
        if self._on_change:
            self._on_change()

    def collect_inputs(self) -> dict:
        return {"directory": self.local_dir_input.text().strip()}

    # Internal helpers
    def _set_ready(self, ready: bool) -> None:
        self._ready = ready
        self._emit_change()

    def _browse_local_directory(self) -> None:
        current_dir = self.local_dir_input.text().strip() or str(Path.home())
        directory = FileDialog.getExistingDirectory(
            parent=self._container, dir=current_dir, caption=_("Select Plugin Directory")
        )
        if directory:
            self.local_dir_input.setText(directory)

    def _validate_local_directory(self) -> None:
        directory_path = self.local_dir_input.text().strip()

        if not directory_path:
            self._discovered_local_plugins = []
            self.local_feedback.clear_and_hide()
            self.local_feedback_container.hide()
            self.plugin_info_text.clear()
            self._set_ready(False)
            return

        path = Path(directory_path)

        if not path.exists():
            self._discovered_local_plugins = []
            self.local_feedback.show_error(_("Directory does not exist"))
            self.local_feedback_container.show()
            self.plugin_info_text.clear()
            self._set_ready(False)
            return

        if not path.is_dir():
            self._discovered_local_plugins = []
            self.local_feedback.show_error(_("Path is not a directory"))
            self.local_feedback_container.show()
            self.plugin_info_text.clear()
            self._set_ready(False)
            return

        # Discover plugin candidates: either the directory itself, or subdirectories
        candidates: list[Path] = []
        if (path / "__init__.py").exists() and (path / "MANIFEST.toml").exists():
            candidates = [path]
        else:
            discovery = PluginDiscovery()
            candidates = discovery.discover(path)

        if not candidates:
            self._discovered_local_plugins = []
            self.local_feedback.show_error(_("No plugins found in directory"))
            self.local_feedback_container.show()
            self.plugin_info_text.clear()
            self._set_ready(False)
            return

        # Validate candidates and collect manifests for display
        from picard.plugin3.manifest import PluginManifest

        validator = PluginValidator()
        valid: list[tuple[str, Path, PluginManifest]] = []
        invalid_errors: list[str] = []
        for c in candidates:
            try:
                name = validator.validate(c)
                with open(c / "MANIFEST.toml", 'rb') as fp:
                    manifest = PluginManifest(c.name, fp)
                valid.append((name, c, manifest))
            except ManifestValidationError as ex:
                invalid_errors.append(f"{c.name}: {ex}")
            except OSError as ex:
                invalid_errors.append(f"{c.name}: {ex}")

        if not valid:
            self._discovered_local_plugins = []
            self.local_feedback.show_error(_("No compatible plugins found in directory"))
            self.local_feedback_container.show()
            self.plugin_info_text.clear()
            self._set_ready(False)
            return

        self._discovered_local_plugins = [p for (_n, p, _m) in valid]

        # Display info: single plugin -> detailed; multiple -> summary list
        if len(valid) == 1:
            _name, plugin_path, manifest = valid[0]
            html_text = build_manifest_info_html(manifest, plugin_path, max_chars=DialogConfig.DESCRIPTION_MAX_CHARS)
            self.plugin_info_text.setHtml(html_text)
            # Hide feedback container for success states to reduce blank space
            self.local_feedback.clear_and_hide()
            self.local_feedback_container.hide()
        else:
            from picard.ui.plugins_manager.manifest_info import build_multiple_manifest_summary_html

            html = build_multiple_manifest_summary_html(valid, invalid_errors)
            self.plugin_info_text.setHtml(html)
            # Hide feedback container for success states to reduce blank space
            self.local_feedback.clear_and_hide()
            self.local_feedback_container.hide()

        self._set_ready(True)
