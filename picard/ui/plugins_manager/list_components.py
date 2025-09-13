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

from PyQt6 import QtCore, QtGui, QtWidgets  # type: ignore[import-not-found]

from picard.const.appdirs import plugin_folder
from picard.i18n import gettext as _
from picard.plugin3.manifest import PluginManifest


DISABLED_ROLE: int = int(QtCore.Qt.ItemDataRole.UserRole) + 1
SLUG_ROLE: int = DISABLED_ROLE + 1


class PluginListModel(QtCore.QAbstractListModel):
    """List model for displaying installed plugins with human-readable names.

    Parameters
    ----------
    items
        Initial list of plugin names.
    disabled
        Set of plugin names that are disabled.
    parent
        Optional parent QObject.
    """

    def __init__(self, items: list[tuple[str, str]] | None = None, disabled: set[str] | None = None, parent=None):
        super().__init__(parent)
        self._items: list[tuple[str, str]] = list(items or [])
        self._disabled: set[str] = set(disabled or set())

    def rowCount(self, parent: QtCore.QModelIndex | None = None) -> int:  # type: ignore[override]
        """Return number of rows in the model."""
        if parent is not None and parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):  # type: ignore[override]
        """Return data for the given role at the specified index."""
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._items):
            return None
        slug, label = self._items[row]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return label
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and slug in self._disabled:
            palette = QtWidgets.QApplication.palette()
            disabled_color = palette.color(
                QtGui.QPalette.ColorGroup.Disabled,
                QtGui.QPalette.ColorRole.Text,
            )
            return disabled_color
        if role == DISABLED_ROLE:
            return slug in self._disabled
        if role == SLUG_ROLE:
            return slug
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:  # type: ignore[override]
        """Return item flags for the given index."""
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def set_plugins(self, items: list[tuple[str, str]]) -> None:
        """Replace the list of plugins (slug, label) and refresh the view.

        Parameters
        ----------
        items
            New list of plugin names.
        """
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def set_disabled(self, disabled: set[str]) -> None:
        """Update the disabled set and refresh font styling.

        Parameters
        ----------
        disabled
            Set of plugin names that should be shown as disabled.
        """
        self._disabled = set(disabled)
        if self._items:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._items) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [QtCore.Qt.ItemDataRole.ForegroundRole])


class PluginItemDelegate(QtWidgets.QStyledItemDelegate):
    """Custom delegate to draw plugin rows with a 'Disabled' pill when applicable."""

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:  # type: ignore[override]
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        is_disabled = bool(index.data(DISABLED_ROLE))
        badge_text = _("Disabled") if is_disabled else ""
        fm = opt.fontMetrics
        spacing = 8
        badge_hpad = 8
        badge_vpad = 2
        badge_rect = QtCore.QRect()
        if is_disabled:
            text_w = fm.horizontalAdvance(badge_text)
            badge_w = text_w + 2 * badge_hpad
            badge_h = fm.height() + 2 * badge_vpad
            r = opt.rect
            badge_x = r.right() - badge_w - spacing
            badge_y = r.top() + (r.height() - badge_h) // 2
            badge_rect = QtCore.QRect(badge_x, badge_y, badge_w, badge_h)

        qstyle: QtWidgets.QStyle | None
        if opt.widget is not None:
            qstyle = opt.widget.style()
        else:
            qstyle = QtWidgets.QApplication.style()
        if qstyle is None:
            super().paint(painter, option, index)
            return
        style: QtWidgets.QStyle = qstyle
        bg_opt = QtWidgets.QStyleOptionViewItem(opt)
        bg_opt.text = ""
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, bg_opt, painter, opt.widget)

        text_rect = QtCore.QRect(opt.rect)
        if is_disabled:
            text_rect.setRight(badge_rect.left() - spacing)

        elided = fm.elidedText(opt.text, QtCore.Qt.TextElideMode.ElideRight, max(0, text_rect.width()))

        text_opt = QtWidgets.QStyleOptionViewItem(opt)
        text_opt.rect = text_rect
        text_opt.text = elided
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, text_opt, painter, opt.widget)

        if is_disabled:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            palette = opt.palette
            if opt.state & QtWidgets.QStyle.StateFlag.State_Selected:
                bg_color = palette.color(QtGui.QPalette.ColorRole.Highlight).lighter(125)
                text_color = palette.color(QtGui.QPalette.ColorRole.HighlightedText)
            else:
                bg_color = palette.color(QtGui.QPalette.ColorRole.Midlight)
                text_color = palette.color(QtGui.QPalette.ColorRole.Text)
            path = QtGui.QPainterPath()
            radius = max(8, badge_rect.height() // 4)
            path.addRoundedRect(QtCore.QRectF(badge_rect), radius, radius)
            painter.fillPath(path, bg_color)
            painter.setPen(text_color)
            painter.drawText(badge_rect, int(QtCore.Qt.AlignmentFlag.AlignCenter), badge_text)
            painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtCore.QSize:  # type: ignore[override]
        return super().sizeHint(option, index)


def get_installed_plugins_with_labels() -> list[tuple[str, str]]:
    """Return installed plugin identifiers and human-readable labels.

    Returns
    -------
    list[tuple[str, str]]
        Pairs of ``(slug, label)``. The label is taken from ``MANIFEST.toml``
        if available, otherwise it falls back to the slug.
    """
    items: list[tuple[str, str]] = []
    base = Path(plugin_folder())
    # Guard against inaccessible plugin directory and manifest parsing errors
    with suppress(OSError, ValueError, KeyError):
        if base.exists():
            for entry in base.iterdir():
                if entry.is_dir():
                    init_ok = (entry / "__init__.py").exists()
                    mani = entry / "MANIFEST.toml"
                    if init_ok and mani.exists():
                        label = entry.name
                        with open(mani, 'rb') as fp:
                            manifest = PluginManifest(entry.name, fp)
                            raw_name = getattr(manifest, 'name', None)
                            if isinstance(raw_name, dict) and raw_name:
                                label = raw_name.get('en', next(iter(raw_name.values())))
                            elif isinstance(raw_name, str) and raw_name.strip():
                                label = raw_name.strip()
                        items.append((entry.name, label))
    return sorted(items, key=lambda p: p[1].lower())
