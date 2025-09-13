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

from PyQt6 import QtWidgets  # type: ignore[import-not-found]


class FeedbackWidget(QtWidgets.QLabel):
    """Reusable feedback label for success or error messages.

    Methods
    -------
    show_error(message)
        Show an error message with red styling.
    show_success(message)
        Show a success message with green styling.
    clear_and_hide()
        Hide the label without clearing text content.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.hide()

    def show_error(self, message: str) -> None:
        """Show an error message.

        Parameters
        ----------
        message
            Message to display.
        """
        self.setText(message)
        self.setStyleSheet("color: #d32f2f; font-size: 11px;")
        self.show()

    def show_success(self, message: str) -> None:
        """Show a success message.

        Parameters
        ----------
        message
            Message to display.
        """
        self.setText(message)
        self.setStyleSheet("color: #2e7d32; font-size: 11px;")
        self.show()

    def clear_and_hide(self) -> None:
        """Hide the label without clearing text content."""
        self.hide()
