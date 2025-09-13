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

import os

from PyQt6 import QtWidgets  # type: ignore[import-not-found]

import pytest

from picard.ui.plugins_manager.widgets import FeedbackWidget


@pytest.fixture(scope="session", autouse=True)
def qtapp() -> QtWidgets.QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


def test_feedback_widget_error() -> None:
    w = FeedbackWidget()
    w.show_error("Error message")
    assert w.text() == "Error message"
    assert "#d32f2f" in w.styleSheet()


def test_feedback_widget_success() -> None:
    w = FeedbackWidget()
    w.show_success("Success message")
    assert w.text() == "Success message"
    assert "#2e7d32" in w.styleSheet()


def test_feedback_widget_hide() -> None:
    w = FeedbackWidget()
    w.show_error("Message")
    w.clear_and_hide()
    # content remains, but widget is hidden
    assert w.text() == "Message"
