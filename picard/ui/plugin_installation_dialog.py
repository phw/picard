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
import re
from urllib.parse import urlparse

from PyQt6 import (
    QtCore,
    QtGui,
    QtWidgets,
)

from picard import log
from picard.i18n import gettext as _
from picard.plugin3.installer import (
    PluginInstallationError,
    PluginInstallationService,
)
from picard.pluginmanager import PluginManager
from picard.util import thread

from picard.ui import PicardDialog, SingletonDialog


DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 400


DISABLED_ROLE: int = int(QtCore.Qt.ItemDataRole.UserRole) + 1


class PluginListModel(QtCore.QAbstractListModel):
    """List model for displaying plugin names with disabled-state styling.

    Parameters
    ----------
    items
        Initial list of plugin names.
    disabled
        Set of plugin names that are disabled.
    parent
        Optional parent QObject.
    """

    def __init__(self, items: list[str] | None = None, disabled: set[str] | None = None, parent=None):
        super().__init__(parent)
        self._items: list[str] = list(items or [])
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
        name = self._items[row]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return name
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and name in self._disabled:
            palette = QtWidgets.QApplication.palette()
            disabled_color = palette.color(
                QtGui.QPalette.ColorGroup.Disabled,
                QtGui.QPalette.ColorRole.Text,
            )
            return disabled_color
        if role == DISABLED_ROLE:
            return name in self._disabled
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:  # type: ignore[override]
        """Return item flags for the given index."""
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def set_plugins(self, items: list[str]) -> None:
        """Replace the list of plugins and refresh the view.

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
        # Initialize style option to respect selection/hover states
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Measure badge if needed
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

        # Draw background for the whole row first
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

        # Compute text rect avoiding badge
        text_rect = QtCore.QRect(opt.rect)
        if is_disabled:
            text_rect.setRight(badge_rect.left() - spacing)

        # Elide text to fit
        elided = fm.elidedText(opt.text, QtCore.Qt.TextElideMode.ElideRight, max(0, text_rect.width()))

        # Draw text using style so colors follow theme/selection
        text_opt = QtWidgets.QStyleOptionViewItem(opt)
        text_opt.rect = text_rect
        text_opt.text = elided
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem, text_opt, painter, opt.widget)

        # Draw badge
        if is_disabled:
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            palette = opt.palette
            if opt.state & QtWidgets.QStyle.StateFlag.State_Selected:
                bg_color = palette.color(QtGui.QPalette.ColorRole.Highlight).lighter(125)
                text_color = palette.color(QtGui.QPalette.ColorRole.HighlightedText)
            else:
                # Subtle neutral pill
                bg_color = palette.color(QtGui.QPalette.ColorRole.Midlight)
                text_color = palette.color(QtGui.QPalette.ColorRole.Text)
            # Fill rounded rect
            path = QtGui.QPainterPath()
            radius = max(8, badge_rect.height() // 4)
            path.addRoundedRect(QtCore.QRectF(badge_rect), radius, radius)
            painter.fillPath(path, bg_color)
            # Draw text centered
            painter.setPen(text_color)
            painter.drawText(badge_rect, int(QtCore.Qt.AlignmentFlag.AlignCenter), badge_text)
            painter.restore()

    def sizeHint(self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> QtCore.QSize:  # type: ignore[override]
        # Base size is sufficient; pill uses same font height
        return super().sizeHint(option, index)


class PluginInstallationDialog(PicardDialog, SingletonDialog):
    """Dialog for installing plugins from git repositories."""

    # Signals
    plugin_installed = QtCore.pyqtSignal(str)  # Emitted when plugin is successfully installed
    installation_failed = QtCore.pyqtSignal(str)  # Emitted when installation fails

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setWindowTitle(_("Install Plugin"))
        self.setModal(True)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        # Git URL validation regex
        self._git_url_pattern = re.compile(r'^https?://(?:[^@/]+@)?(?:[^:/]+)(?::\d+)?/[^/]+/[^/]+(?:\.git)?/?$')

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the user interface."""
        main_layout = QtWidgets.QHBoxLayout(self)

        # Left pane: Installed plugins
        left_container = QtWidgets.QGroupBox(_("Installed Plugins"), self)
        left_layout = QtWidgets.QVBoxLayout(left_container)

        self.plugins_view = QtWidgets.QListView(self)
        self.plugins_model = PluginListModel([], set(), self)
        self.plugins_view.setModel(self.plugins_model)
        self.plugins_view.setItemDelegate(PluginItemDelegate(self.plugins_view))
        self.plugins_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        left_layout.addWidget(self.plugins_view)

        plugins_buttons_layout = QtWidgets.QHBoxLayout()
        self.toggle_button = QtWidgets.QPushButton(_("Enable"))
        self.uninstall_button = QtWidgets.QPushButton(_("Uninstall"))
        plugins_buttons_layout.addWidget(self.toggle_button)
        plugins_buttons_layout.addWidget(self.uninstall_button)
        left_layout.addLayout(plugins_buttons_layout)

        # Initialize plugin manager and list
        self._plugin_manager = PluginManager()
        with suppress(OSError, ImportError, RuntimeError):
            # Attempt loading from default user plugin dir
            self._plugin_manager.load_plugins_from_directory(self._plugin_manager.plugins_directory)
        self._disabled_plugins: set[str] = set()
        self._refresh_plugins_list()
        # Inject two demo items for visual testing
        self._inject_demo_plugins()

        # Wire up selection and actions
        if self.plugins_view.selectionModel():
            self.plugins_view.selectionModel().selectionChanged.connect(self._on_plugin_selection_changed)
        self.toggle_button.clicked.connect(self._toggle_selected_plugin)
        self.uninstall_button.clicked.connect(self._uninstall_selected_plugin)
        self._update_plugin_action_buttons()

        # Right pane: existing install UI
        right_container = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(right_container)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Title and description
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

        # URL inputs section (stackable up to 5)
        self.max_urls = 5
        self.url_inputs: list[QtWidgets.QLineEdit] = []
        self.url_grid = QtWidgets.QGridLayout()
        self.url_grid.setHorizontalSpacing(8)
        self.url_grid.setVerticalSpacing(6)

        # First row with label
        self._add_url_input(initial=True)

        # Plus button (moves down as rows are added) placed to the right of input
        self.add_button = QtWidgets.QToolButton()
        self.add_button.setText("+")
        self.add_button.setToolTip(_("Add another repository URL"))
        self.add_button.clicked.connect(self._on_add_url_clicked)
        self._reposition_add_button()

        layout.addLayout(self.url_grid)

        # URL validation feedback (stabilized height)
        self.feedback_container = QtWidgets.QFrame()
        self.feedback_container.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        feedback_container_layout = QtWidgets.QVBoxLayout(self.feedback_container)
        feedback_container_layout.setContentsMargins(0, 0, 0, 0)
        feedback_container_layout.setSpacing(0)

        self.url_feedback = QtWidgets.QLabel()
        self.url_feedback.setStyleSheet("color: #d32f2f; font-size: 11px;")
        self.url_feedback.setWordWrap(True)
        self.url_feedback.hide()
        feedback_container_layout.addWidget(self.url_feedback)

        # Reserve a stable minimum height for feedback
        feedback_min_height = self.fontMetrics().lineSpacing() + 6
        self.feedback_container.setMinimumHeight(feedback_min_height)
        self.feedback_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.feedback_container)

        # Always-visible progress area
        self.progress_group = QtWidgets.QGroupBox(_("Installation Progress"))
        progress_layout = QtWidgets.QVBoxLayout(self.progress_group)

        self.progress_bar = QtWidgets.QProgressBar()
        # Idle state: disabled and slightly visible
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setEnabled(False)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QtWidgets.QLabel()
        self.progress_label.setWordWrap(True)
        # Reserve one line height so the group keeps steady height even with no text
        self.progress_label.setMinimumHeight(self.fontMetrics().height())
        self.progress_label.setText("")
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(self.progress_group)

        # Error display (separate from progress, shown when needed)
        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet("color: #d32f2f; background-color: #ffebee; padding: 8px; border-radius: 4px;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Button box
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(_("Install"))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.button_box)
        # Keep right pane content stuck to the top when dialog grows vertically
        layout.addStretch(1)

        # Assemble panes
        main_layout.addWidget(left_container, stretch=1)
        main_layout.addWidget(right_container, stretch=2)

    def _connect_signals(self):
        """Connect UI signals."""
        self.button_box.accepted.connect(self._start_installation)
        self.button_box.rejected.connect(self.reject)

    def _on_add_url_clicked(self) -> None:
        """Add a new URL input row when + is clicked."""
        if len(self.url_inputs) < self.max_urls:
            new_input = self._add_url_input(initial=False)
            self._reposition_add_button()
            # Focus the newly created input for immediate typing
            if new_input is not None:
                new_input.setFocus()
        self._validate_urls()

    def _add_url_input(self, initial: bool) -> QtWidgets.QLineEdit:
        """Create and add a URL input row.

        Parameters
        ----------
        initial
            Whether this is the first row. If true a label is added.
        """
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
        url_input.textChanged.connect(lambda _t: self._validate_urls())
        self.url_grid.addWidget(url_input, row, 2)
        self.url_inputs.append(url_input)

        # Backwards compatibility alias for tests/utilities referencing single input
        if initial:
            self.url_input = url_input
        return url_input

    def _reposition_add_button(self) -> None:
        """Place the + button to the right of the last input row; disable at max rows."""
        last_row_index = len(self.url_inputs) - 1
        if last_row_index < 0:
            return
        # Move the button widget to the new position
        with suppress(RuntimeError):
            self.url_grid.removeWidget(self.add_button)
        self.url_grid.addWidget(self.add_button, last_row_index, 3)
        # Disable instead of hiding when at maximum
        self.add_button.setEnabled(len(self.url_inputs) < self.max_urls)
        self.add_button.show()

    def _validate_urls(self) -> None:
        """Validate all entered URLs, de-duplicate, and update the UI feedback."""
        texts = [w.text().strip() for w in self.url_inputs]
        non_empty = [t for t in texts if t]
        invalid = [t for t in non_empty if not self._is_valid_git_url(t)]

        if invalid:
            self._show_error_feedback(_("Please enter a valid git repository URL (e.g., https://github.com/user/repo)"))
            self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        if not non_empty:
            self._hide_feedback()
            self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        count_unique = len({t for t in non_empty})
        self._show_success_feedback(_("{count} valid URL(s) detected").format(count=count_unique))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    # Legacy single-URL validator preserved for test compatibility
    def _validate_url(self, url: str) -> None:
        url = url.strip()
        if self.url_inputs:
            self.url_inputs[0].setText(url)
        self._validate_urls()

    def _is_valid_git_url(self, url: str) -> bool:
        """Check if the URL is a valid git repository URL."""
        if not url:
            return False

        # Basic URL validation
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
        except (ValueError, TypeError):
            return False

        # Check if it looks like a git repository URL
        return bool(self._git_url_pattern.match(url))

    def _show_error_feedback(self, message: str) -> None:
        """Show error feedback message."""
        self.url_feedback.setText(message)
        self.url_feedback.setStyleSheet("color: #d32f2f; font-size: 11px;")
        self.url_feedback.show()

    def _show_success_feedback(self, message: str) -> None:
        """Show success feedback message."""
        self.url_feedback.setText(message)
        self.url_feedback.setStyleSheet("color: #2e7d32; font-size: 11px;")
        self.url_feedback.show()

    def _hide_feedback(self) -> None:
        """Hide URL feedback message."""
        self.url_feedback.hide()

    def _start_installation(self) -> None:
        """Start the plugin installation process."""
        urls = self._collect_valid_urls()
        if not urls:
            return

        # Hide previous messages
        self.error_label.hide()

        # Show progress
        self._hide_feedback()
        # Activate progress
        self.progress_bar.setEnabled(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_label.setText(_("Starting installation of {n} plugin(s)...").format(n=len(urls)))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setEnabled(False)

        # Start installation in background thread
        self._install_plugins_async(urls)

    def _install_plugins_async(self, urls: list[str]) -> None:
        """Install one or more plugins asynchronously."""

        def install_worker():
            try:
                installer = PluginInstallationService()
                success_count = 0
                error_count = 0
                seen: set[str] = set()

                def progress_cb(message: str) -> None:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_update_progress",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, message),
                    )

                for url in urls:
                    if url in seen:
                        continue
                    seen.add(url)

                    try:
                        installed_names = installer.install_from_git(url, progress=progress_cb)
                        success_count += len(installed_names)
                        QtCore.QMetaObject.invokeMethod(
                            self,
                            "_installation_success",
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(str, url),
                        )
                    except PluginInstallationError as ex:
                        error_count += 1
                        QtCore.QMetaObject.invokeMethod(
                            self,
                            "_installation_failed",
                            QtCore.Qt.ConnectionType.QueuedConnection,
                            QtCore.Q_ARG(str, str(ex)),
                        )

                # Refresh plugin list after installation attempts
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_refresh_plugins_list",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_installation_complete",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(int, success_count),
                    QtCore.Q_ARG(int, error_count),
                )

            except (OSError, ValueError, RuntimeError, ImportError) as e:
                QtCore.QMetaObject.invokeMethod(
                    self, "_installation_failed", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(str, str(e))
                )

        thread.run_task(install_worker)

    @QtCore.pyqtSlot(str)
    def _update_progress(self, message: str) -> None:
        """Update progress message."""
        self.progress_label.setText(message)

    @QtCore.pyqtSlot(str)
    def _installation_success(self, url: str) -> None:
        """Handle successful installation."""
        # Show completion in the existing progress area
        # Show completion within progress area
        self.progress_bar.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_label.setText(_("Plugin installed successfully!"))

        # Re-enable buttons
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(_("Close"))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).hide()

        # Emit signal
        self.plugin_installed.emit(url)

        log.info("Plugin installed successfully from %s", url)

    @QtCore.pyqtSlot(str)
    def _installation_failed(self, error_message: str) -> None:
        """Handle installation failure."""
        # Stop progress and show error below
        self.progress_bar.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("")
        self.error_label.setText(_("Installation failed: {}").format(error_message))
        self.error_label.show()

        # Re-enable buttons
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(_("Install"))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setEnabled(True)

        # Emit signal
        self.installation_failed.emit(error_message)

        log.error("Plugin installation failed: %s", error_message)

    # --- Installed plugins pane logic ---
    def _refresh_plugins_list(self) -> None:
        names = [p.name for p in getattr(self._plugin_manager, 'plugins', [])]
        self.plugins_model.set_plugins(names)
        self.plugins_model.set_disabled(self._disabled_plugins)
        self._update_plugin_action_buttons()

    def _selected_plugin_name(self) -> str | None:
        indexes = self.plugins_view.selectedIndexes()
        if not indexes:
            return None
        return self.plugins_model.data(indexes[0], QtCore.Qt.ItemDataRole.DisplayRole)

    def _on_plugin_selection_changed(self) -> None:
        self._update_plugin_action_buttons()

    def _update_plugin_action_buttons(self) -> None:
        name = self._selected_plugin_name()
        if not name:
            self.toggle_button.setEnabled(False)
            self.toggle_button.setText(_("Enable"))
            self.uninstall_button.setEnabled(False)
            return
        is_disabled = name in self._disabled_plugins
        self.toggle_button.setEnabled(True)
        self.toggle_button.setText(_("Enable") if is_disabled else _("Disable"))
        self.uninstall_button.setEnabled(True)

    def _toggle_selected_plugin(self) -> None:
        name = self._selected_plugin_name()
        if not name:
            return
        if name in self._disabled_plugins:
            self._disabled_plugins.remove(name)
        else:
            self._disabled_plugins.add(name)
        self.plugins_model.set_disabled(self._disabled_plugins)
        self._update_plugin_action_buttons()

    def _uninstall_selected_plugin(self) -> None:
        name = self._selected_plugin_name()
        if not name:
            return
        with suppress(OSError, RuntimeError, AttributeError):
            plugin = next((p for p in self._plugin_manager.plugins if p.name == name), None)
            module_name = plugin.module_name if plugin else None
            if module_name:
                self._plugin_manager.remove_plugin(module_name)
        self._disabled_plugins.discard(name)
        self._refresh_plugins_list()

    def _reset_url_inputs(self) -> None:
        """Reset URL inputs to a single empty row and refresh UI state."""
        # Remove all rows from grid except keep first slot for label and first input
        while len(self.url_inputs) > 1:
            line_edit = self.url_inputs.pop()
            self.url_grid.removeWidget(line_edit)
            line_edit.deleteLater()
        if self.url_inputs:
            self.url_inputs[0].clear()
        self._reposition_add_button()
        self._validate_urls()

    def reject(self) -> None:  # type: ignore[override]
        """Handle Cancel: reset inputs then close the dialog."""
        self._reset_url_inputs()
        super().reject()

    def _inject_demo_plugins(self) -> None:
        """Insert two demo items: one enabled, one disabled for UI testing."""
        demo_enabled = "Demo Plugin"
        demo_disabled = "Demo Disabled Plugin"
        # Merge with current list without duplicates
        current = [p.name for p in getattr(self._plugin_manager, 'plugins', [])]
        if demo_enabled not in current:
            current.append(demo_enabled)
        if demo_disabled not in current:
            current.append(demo_disabled)
        self.plugins_model.set_plugins(current)
        self._disabled_plugins.add(demo_disabled)
        self.plugins_model.set_disabled(self._disabled_plugins)

    @QtCore.pyqtSlot(int, int)
    def _installation_complete(self, success_count: int, error_count: int) -> None:
        """Show overall installation results.

        Parameters
        ----------
        success_count
            Number of successfully installed plugins.
        error_count
            Number of plugins that failed to install.
        """
        self.progress_bar.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success_count > 0 and error_count == 0 else 0)
        self.progress_label.setText(
            _("Completed: {ok} success(es), {err} error(s)").format(ok=success_count, err=error_count)
        )
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(_("Close"))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).hide()

    def _collect_valid_urls(self) -> list[str]:
        """Collect and return unique valid URLs in input order."""
        texts = [w.text().strip() for w in self.url_inputs]
        non_empty = [t for t in texts if t]
        valid = [t for t in non_empty if self._is_valid_git_url(t)]
        seen: set[str] = set()
        unique: list[str] = []
        for u in valid:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique

    def get_url(self) -> str:
        """Get the entered URL."""
        return self.url_inputs[0].text().strip() if self.url_inputs else ""

    def set_url(self, url: str) -> None:
        """Set the URL input."""
        if not self.url_inputs:
            self._add_url_input(initial=True)
        self.url_inputs[0].setText(url)
