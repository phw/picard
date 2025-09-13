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
from typing import Callable

from PyQt6 import QtWidgets  # type: ignore[import-not-found]

from picard.i18n import gettext as _

from picard.ui.plugins_manager.config import DialogConfig
from picard.ui.plugins_manager.validation import UrlValidator
from picard.ui.plugins_manager.widgets import FeedbackWidget


class RepositoryUrlInputs(QtWidgets.QWidget):
    """Widget managing multiple git repository URL inputs and feedback."""

    def __init__(self, parent=None, *, validator: UrlValidator | None = None):
        super().__init__(parent)
        self._validator = validator or UrlValidator()
        self.max_urls: int = DialogConfig.MAX_URLS
        self.url_inputs: list[QtWidgets.QLineEdit] = []

        layout = QtWidgets.QVBoxLayout(self)

        self.url_grid = QtWidgets.QGridLayout()
        self.url_grid.setHorizontalSpacing(8)
        self.url_grid.setVerticalSpacing(6)
        layout.addLayout(self.url_grid)

        # First row
        self._add_url_input(initial=True)

        # + button
        self.add_button = QtWidgets.QToolButton()
        self.add_button.setText("+")
        self.add_button.setToolTip(_("Add another repository URL"))
        self.add_button.clicked.connect(self._on_add_url_clicked)
        self._reposition_add_button()

        # Feedback
        self.feedback_container = QtWidgets.QFrame()
        self.feedback_container.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        feedback_container_layout = QtWidgets.QVBoxLayout(self.feedback_container)
        feedback_container_layout.setContentsMargins(0, 0, 0, 0)
        feedback_container_layout.setSpacing(0)

        self.url_feedback = FeedbackWidget()
        feedback_container_layout.addWidget(self.url_feedback)

        feedback_min_height = self.fontMetrics().lineSpacing() + 6
        self.feedback_container.setMinimumHeight(feedback_min_height)
        self.feedback_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.feedback_container)

        layout.addStretch(1)

        self._on_change: Callable[[], None] | None = None

    def set_on_change(self, cb: Callable[[], None]) -> None:
        self._on_change = cb

    def _on_add_url_clicked(self) -> None:
        if len(self.url_inputs) < self.max_urls:
            self._add_url_input(initial=False)
            self._reposition_add_button()
        self.validate()

    def _add_url_input(self, initial: bool) -> QtWidgets.QLineEdit:
        row = len(self.url_inputs)
        if initial:
            url_label = QtWidgets.QLabel(_("Repository URL:"))
            url_label.setMinimumWidth(120)
            self.url_grid.addWidget(url_label, row, 1)
        else:
            spacer = QtWidgets.QWidget()
            spacer.setFixedWidth(120)
            self.url_grid.addWidget(spacer, row, 1)

        url_input = QtWidgets.QLineEdit()
        url_input.setPlaceholderText(_("https://github.com/user/picard-plugin-example"))
        url_input.textChanged.connect(lambda _t: self.validate())
        self.url_grid.addWidget(url_input, row, 2)
        self.url_inputs.append(url_input)
        if initial:
            # public alias for first input to preserve tests
            self.url_input = url_input
        return url_input

    def _reposition_add_button(self) -> None:
        last_row_index = len(self.url_inputs) - 1
        if last_row_index < 0:
            return
        with suppress(RuntimeError):
            self.url_grid.removeWidget(self.add_button)
        self.url_grid.addWidget(self.add_button, last_row_index, 3)
        self.add_button.setEnabled(len(self.url_inputs) < self.max_urls)
        self.add_button.show()

    def validate(self) -> None:
        texts = [w.text().strip() for w in self.url_inputs]
        non_empty = [t for t in texts if t]
        invalid = [t for t in non_empty if not self._validator.is_valid_git_url(t)]

        if invalid:
            self.url_feedback.show_error(
                _("Please enter a valid git repository URL (e.g., https://github.com/user/repo)")
            )
            self.feedback_container.show()
            if self._on_change:
                self._on_change()
            return

        if not non_empty:
            self.url_feedback.clear_and_hide()
            self.feedback_container.hide()
            if self._on_change:
                self._on_change()
            return

        # Hide feedback container for success/idle states to reduce blank space
        self.url_feedback.clear_and_hide()
        self.feedback_container.hide()
        if self._on_change:
            self._on_change()

    def valid_urls(self) -> list[str]:
        texts = [w.text().strip() for w in self.url_inputs]
        non_empty = [t for t in texts if t]
        valid = [t for t in non_empty if self._validator.is_valid_git_url(t)]
        seen: set[str] = set()
        unique: list[str] = []
        for u in valid:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    def reset(self) -> None:
        while len(self.url_inputs) > 1:
            line_edit = self.url_inputs.pop()
            self.url_grid.removeWidget(line_edit)
            line_edit.deleteLater()
        if self.url_inputs:
            self.url_inputs[0].clear()
        self._reposition_add_button()
        self.validate()
