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

import os

from PyQt6 import QtCore, QtWidgets  # type: ignore[import-not-found]

import pytest

from picard.ui.plugins_manager.list_components import (
    DISABLED_ROLE,
    SLUG_ROLE,
    PluginItemDelegate,
    PluginListModel,
)


@pytest.fixture(scope="session", autouse=True)
def qtapp() -> QtWidgets.QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]


def test_model_basic_roles() -> None:
    model = PluginListModel(items=[("slug1", "Plugin One"), ("slug2", "Plugin Two")], disabled={"slug2"})
    assert model.rowCount() == 2

    idx0 = model.index(0, 0)
    idx1 = model.index(1, 0)

    assert model.data(idx0, QtCore.Qt.ItemDataRole.DisplayRole) == "Plugin One"
    assert model.data(idx0, SLUG_ROLE) == "slug1"
    assert model.data(idx0, DISABLED_ROLE) is False

    assert model.data(idx1, QtCore.Qt.ItemDataRole.DisplayRole) == "Plugin Two"
    assert model.data(idx1, SLUG_ROLE) == "slug2"
    assert model.data(idx1, DISABLED_ROLE) is True


def test_model_setters_emit_changes(qtapp: QtWidgets.QApplication) -> None:
    model = PluginListModel(items=[("slug1", "Plugin One"), ("slug2", "Plugin Two")], disabled=set())

    # Track dataChanged emissions
    changes: list[tuple[int, int]] = []

    def on_data_changed(tl: QtCore.QModelIndex, br: QtCore.QModelIndex) -> None:
        changes.append((tl.row(), br.row()))

    model.dataChanged.connect(on_data_changed)
    model.set_disabled({"slug1"})

    # Ensure dataChanged emitted at least once across rows 0..1
    assert changes, "dataChanged should be emitted"
    tl, br = changes[-1]
    assert tl == 0 and br == 1

    # Replace plugins and ensure rowCount reflects change
    model.set_plugins([("a", "A"), ("b", "B"), ("c", "C")])
    assert model.rowCount() == 3


def test_delegate_size_hint_returns_base(qtapp: QtWidgets.QApplication) -> None:
    view = QtWidgets.QListView()
    model = PluginListModel(items=[("slug1", "Plugin One")], disabled=set())
    view.setModel(model)
    delegate = PluginItemDelegate(view)
    opt = QtWidgets.QStyleOptionViewItem()
    idx = model.index(0, 0)
    size = delegate.sizeHint(opt, idx)
    assert size.isValid()
