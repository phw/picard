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

from PyQt6 import QtCore, QtWidgets  # type: ignore[import-not-found]

from picard.i18n import gettext as _
from picard.plugin3.installer import (
    ManifestValidationError,
    PluginInstallationError,
    RepositoryCloneError,
)
from picard.util import thread

from picard.ui.plugins_manager.config import DialogConfig
from picard.ui.plugins_manager.manifest_info import (
    build_manifest_info_html,
    build_multiple_manifest_summary_html,
)
from picard.ui.plugins_manager.preview import GitRepositoryPreviewer
from picard.ui.plugins_manager.protocols import InstallationSource
from picard.ui.plugins_manager.repository_url_inputs import RepositoryUrlInputs
from picard.ui.plugins_manager.validation import UrlValidator
from picard.ui.plugins_manager.widgets import FeedbackWidget


class GitInstallTab(InstallationSource):
    """Installation source for Git repositories."""

    def __init__(self, parent=None, *, validator: UrlValidator | None = None):
        self._container = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(self._container)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        title_label = QtWidgets.QLabel(_("Install Plugin from Git Repository"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        desc_label = QtWidgets.QLabel(
            _(
                "Enter the URL of a git repository containing a Picard plugin. "
                "The repository should contain one or more plugin directories with "
                "MANIFEST.toml files."
            )
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)

        self._inputs = RepositoryUrlInputs(self._container, validator=validator)
        layout.addWidget(self._inputs)
        # Preview feedback and plugin info (mirrors LocalInstallTab)
        self.preview_feedback_container = QtWidgets.QFrame()
        preview_feedback_layout = QtWidgets.QVBoxLayout(self.preview_feedback_container)
        preview_feedback_layout.setContentsMargins(0, 0, 0, 0)
        preview_feedback_layout.setSpacing(0)
        self.preview_feedback = FeedbackWidget()
        preview_feedback_layout.addWidget(self.preview_feedback)
        layout.addWidget(self.preview_feedback_container)

        self.plugin_info_group = QtWidgets.QGroupBox(_("Plugin Information"))
        plugin_info_layout = QtWidgets.QVBoxLayout(self.plugin_info_group)
        self.plugin_info_text = QtWidgets.QTextEdit()
        self.plugin_info_text.setReadOnly(True)
        self.plugin_info_text.setMaximumHeight(120)
        self.plugin_info_text.setPlaceholderText(
            _("Plugin information will appear here when a valid repository is analyzed")
        )
        plugin_info_layout.addWidget(self.plugin_info_text)
        layout.addWidget(self.plugin_info_group)

        layout.addStretch(1)

        # Preview machinery
        self._previewer = GitRepositoryPreviewer()
        self._preview_token: int = 0

    def widget(self) -> QtWidgets.QWidget:
        return self._container

    def is_ready(self) -> bool:
        return len(self._inputs.valid_urls()) > 0

    def reset(self) -> None:
        self._inputs.reset()

    def on_change(self, cb: Callable[[], None]) -> None:
        def wrapped() -> None:
            cb()
            self._maybe_preview()

        self._inputs.set_on_change(wrapped)

    def collect_inputs(self) -> dict:
        return {"urls": self._inputs.valid_urls()}

    # Convenience helpers for dialog/back-compat shims
    def validate(self) -> None:
        self._inputs.validate()
        self._maybe_preview()

    def valid_urls(self) -> list[str]:
        return self._inputs.valid_urls()

    def set_first_url(self, url: str) -> None:
        if getattr(self._inputs, 'url_inputs', None):
            self._inputs.url_inputs[0].setText(url)

    def show_error_feedback(self, message: str) -> None:
        self._inputs.url_feedback.show_error(message)

    def show_success_feedback(self, message: str) -> None:
        self._inputs.url_feedback.show_success(message)

    def hide_feedback(self) -> None:
        self._inputs.url_feedback.clear_and_hide()

    # --- Preview logic ---
    def _maybe_preview(self) -> None:
        urls = self._inputs.valid_urls()
        if not urls:
            self.preview_feedback.clear_and_hide()
            self.preview_feedback_container.hide()
            self.plugin_info_text.clear()
            return
        self._start_preview(urls)

    def _start_preview(self, urls: list[str]) -> None:
        # Increment token to cancel older runs
        self._preview_token += 1
        token = self._preview_token
        self.plugin_info_text.setHtml(_("Analyzing repositories..."))
        self.preview_feedback.clear_and_hide()
        self.preview_feedback_container.hide()

        def worker() -> tuple[str, int, bool]:
            sections: list[str] = []
            total_valid_plugins = 0
            any_errors = False
            for url in urls:
                try:
                    valid, invalid_errors = self._previewer.analyze(url, progress=None)
                except (RepositoryCloneError, ManifestValidationError, PluginInstallationError) as ex:
                    sections.append(f"<b>{url}</b><br><span style='color:#d32f2f'>{ex}</span>")
                    any_errors = True
                    continue

                # Build section for this URL
                if len(valid) == 1:
                    _name, plugin_path, manifest = valid[0]
                    html_text = build_manifest_info_html(
                        manifest, plugin_path, max_chars=DialogConfig.DESCRIPTION_MAX_CHARS
                    )
                    section = f"<div><b>{url}</b><br>{html_text}</div>"
                else:
                    section = (
                        f"<div><b>{url}</b><br>"
                        + build_multiple_manifest_summary_html(valid, invalid_errors)
                        + "</div>"
                    )
                sections.append(section)
                total_valid_plugins += len(valid)
                any_errors = any_errors or bool(invalid_errors)

            combined_html = "<hr>".join(sections) if sections else ""
            return (combined_html, total_valid_plugins, any_errors)

        def apply(result=None, error=None) -> None:
            if token != self._preview_token:
                return
            if error:
                self.preview_feedback.show_error(_("Error analyzing repositories: {error}").format(error=str(error)))
                self.preview_feedback_container.show()
                return
            if result:
                combined_html, total_valid_plugins, any_errors = result
                if combined_html:
                    self.plugin_info_text.setHtml(combined_html)
                else:
                    self.plugin_info_text.clear()
                if any_errors and total_valid_plugins == 0:
                    self.preview_feedback.show_error(_("No compatible plugins found in repositories"))
                    self.preview_feedback_container.show()
                else:
                    # Hide feedback container for success states to reduce blank space
                    self.preview_feedback.clear_and_hide()
                    self.preview_feedback_container.hide()

        thread.run_task(worker, apply)
