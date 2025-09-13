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

from picard.ui.plugins_manager.protocols import InstallationSource
from picard.ui.plugins_manager.repository_url_inputs import RepositoryUrlInputs
from picard.ui.plugins_manager.validation import UrlValidator


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
        layout.addStretch(1)

    def widget(self) -> QtWidgets.QWidget:
        return self._container

    def is_ready(self) -> bool:
        return len(self._inputs.valid_urls()) > 0

    def reset(self) -> None:
        self._inputs.reset()

    def on_change(self, cb: Callable[[], None]) -> None:
        self._inputs.set_on_change(cb)

    def collect_inputs(self) -> dict:
        return {"urls": self._inputs.valid_urls()}

    # Convenience helpers for dialog/back-compat shims
    def validate(self) -> None:
        self._inputs.validate()

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
