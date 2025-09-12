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
from picard.tagger import Tagger
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
    """Dialog for installing plugins from git repositories or local directories."""

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

        # Current installation method
        self._current_method = "git"  # "git" or "local"

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

        # Initialize plugin manager v3 and list
        self._plugin_manager3 = Tagger.instance().pluginmanager3
        self._disabled_plugins: set[str] = set()
        self._refresh_plugins_list()

        # Wire up selection and actions
        if self.plugins_view.selectionModel():
            self.plugins_view.selectionModel().selectionChanged.connect(self._on_plugin_selection_changed)
        self.toggle_button.clicked.connect(self._toggle_selected_plugin)
        self.uninstall_button.clicked.connect(self._uninstall_selected_plugin)
        self._update_plugin_action_buttons()

        # Right pane: Tabbed installation interface
        right_container = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(right_container)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Create tab widget
        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget)

        # Git installation tab
        self._setup_git_tab()

        # Local installation tab
        self._setup_local_tab()

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

    def _setup_git_tab(self):
        """Set up the git repository installation tab."""
        git_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(git_tab)
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

        # Add stretch to push content to top
        layout.addStretch(1)

        self.tab_widget.addTab(git_tab, _("From Git Repository"))

    def _setup_local_tab(self):
        """Set up the local directory installation tab."""
        local_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(local_tab)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        # Title and description
        title_label = QtWidgets.QLabel(_("Install Plugin from Local Directory"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        desc_label = QtWidgets.QLabel(
            _(
                "Select a local directory containing a Picard plugin. "
                "The directory should contain a MANIFEST.toml file and "
                "follow the plugin package structure."
            )
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)

        # Directory selection
        dir_layout = QtWidgets.QHBoxLayout()
        dir_label = QtWidgets.QLabel(_("Plugin Directory:"))
        dir_label.setMinimumWidth(120)
        dir_layout.addWidget(dir_label)

        self.local_dir_input = QtWidgets.QLineEdit()
        self.local_dir_input.setPlaceholderText(_("Select a directory containing a plugin"))
        self.local_dir_input.textChanged.connect(self._validate_local_directory)
        dir_layout.addWidget(self.local_dir_input, stretch=1)

        self.browse_button = QtWidgets.QPushButton(_("Browse..."))
        self.browse_button.clicked.connect(self._browse_local_directory)
        dir_layout.addWidget(self.browse_button)

        layout.addLayout(dir_layout)

        # Local directory validation feedback
        self.local_feedback_container = QtWidgets.QFrame()
        self.local_feedback_container.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        local_feedback_layout = QtWidgets.QVBoxLayout(self.local_feedback_container)
        local_feedback_layout.setContentsMargins(0, 0, 0, 0)
        local_feedback_layout.setSpacing(0)

        self.local_feedback = QtWidgets.QLabel()
        self.local_feedback.setStyleSheet("color: #d32f2f; font-size: 11px;")
        self.local_feedback.setWordWrap(True)
        self.local_feedback.hide()
        local_feedback_layout.addWidget(self.local_feedback)

        # Reserve a stable minimum height for feedback
        local_feedback_min_height = self.fontMetrics().lineSpacing() + 6
        self.local_feedback_container.setMinimumHeight(local_feedback_min_height)
        self.local_feedback_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.local_feedback_container)

        # Plugin info display
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

        # Add stretch to push content to top
        layout.addStretch(1)

        self.tab_widget.addTab(local_tab, _("From Local Directory"))

    def _connect_signals(self):
        """Connect UI signals."""
        self.button_box.accepted.connect(self._start_installation)
        self.button_box.rejected.connect(self.reject)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change to update current method and button state."""
        if index == 0:  # Git tab
            self._current_method = "git"
        else:  # Local tab
            self._current_method = "local"
        self._update_install_button_state()

    def _browse_local_directory(self) -> None:
        """Open directory browser for local plugin selection."""
        from picard.ui.util import FileDialog

        current_dir = self.local_dir_input.text().strip()
        if not current_dir:
            current_dir = str(Path.home())

        directory = FileDialog.getExistingDirectory(parent=self, dir=current_dir, caption=_("Select Plugin Directory"))

        if directory:
            self.local_dir_input.setText(directory)

    def _validate_local_directory(self) -> None:
        """Validate the selected local directory and update UI feedback."""
        directory_path = self.local_dir_input.text().strip()

        if not directory_path:
            self._hide_local_feedback()
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        path = Path(directory_path)

        # Check if path exists and is a directory
        if not path.exists():
            self._show_local_error_feedback(_("Directory does not exist"))
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        if not path.is_dir():
            self._show_local_error_feedback(_("Path is not a directory"))
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        # Check for required plugin files
        manifest_path = path / "MANIFEST.toml"
        init_path = path / "__init__.py"

        if not manifest_path.exists():
            self._show_local_error_feedback(_("MANIFEST.toml not found in directory"))
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        if not init_path.exists():
            self._show_local_error_feedback(_("__init__.py not found in directory"))
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        # Try to read and validate manifest
        try:
            from picard.plugin3.manager import _is_plugin_compatible
            from picard.plugin3.manifest import PluginManifest

            with open(manifest_path, 'rb') as manifest_file:
                manifest = PluginManifest(path.name, manifest_file)

            # Check API compatibility
            if not _is_plugin_compatible(manifest.api_versions):
                from picard import api_versions_tuple

                error_msg = (
                    f"Plugin is not compatible with this version of Picard. "
                    f"Plugin requires API versions: {[str(v) for v in manifest.api_versions]}, "
                    f"but Picard supports: {[str(v) for v in api_versions_tuple]}"
                )
                self._show_local_error_feedback(error_msg)
                self._clear_plugin_info()
                self._update_install_button_state()
                return

            # Display plugin information
            self._display_plugin_info(manifest, path)
            self._show_local_success_feedback(_("Valid plugin directory detected"))
            self._update_install_button_state()

        except Exception as e:
            self._show_local_error_feedback(_("Invalid plugin manifest: {}").format(str(e)))
            self._clear_plugin_info()
            self._update_install_button_state()

    def _display_plugin_info(self, manifest, path: Path) -> None:
        """Display plugin information in the info text area."""
        info_lines = []

        # Plugin name
        if hasattr(manifest, 'name') and manifest.name:
            if isinstance(manifest.name, dict):
                name = manifest.name.get('en', list(manifest.name.values())[0] if manifest.name else 'Unknown')
            else:
                name = str(manifest.name)
            info_lines.append(f"<b>Name:</b> {name}")

        # Authors
        if hasattr(manifest, 'authors') and manifest.authors:
            authors = ', '.join(manifest.authors) if isinstance(manifest.authors, list) else str(manifest.authors)
            info_lines.append(f"<b>Authors:</b> {authors}")

        # Description
        if hasattr(manifest, 'description') and manifest.description:
            if isinstance(manifest.description, dict):
                desc = manifest.description.get(
                    'en', list(manifest.description.values())[0] if manifest.description else 'No description'
                )
            else:
                desc = str(manifest.description)
            info_lines.append(f"<b>Description:</b> {desc}")

        # API versions
        if hasattr(manifest, 'api') and manifest.api:
            api_versions = ', '.join(manifest.api) if isinstance(manifest.api, list) else str(manifest.api)
            info_lines.append(f"<b>API Versions:</b> {api_versions}")

        # License
        if hasattr(manifest, 'license') and manifest.license:
            info_lines.append(f"<b>License:</b> {manifest.license}")

        # Directory path
        info_lines.append(f"<b>Directory:</b> {path}")

        self.plugin_info_text.setHtml('<br>'.join(info_lines))

    def _clear_plugin_info(self) -> None:
        """Clear the plugin information display."""
        self.plugin_info_text.clear()

    def _show_local_error_feedback(self, message: str) -> None:
        """Show error feedback for local directory validation."""
        self.local_feedback.setText(message)
        self.local_feedback.setStyleSheet("color: #d32f2f; font-size: 11px;")
        self.local_feedback.show()

    def _show_local_success_feedback(self, message: str) -> None:
        """Show success feedback for local directory validation."""
        self.local_feedback.setText(message)
        self.local_feedback.setStyleSheet("color: #2e7d32; font-size: 11px;")
        self.local_feedback.show()

    def _hide_local_feedback(self) -> None:
        """Hide local directory feedback message."""
        self.local_feedback.hide()

    def _update_install_button_state(self) -> None:
        """Update the install button state based on current method and validation."""
        if self._current_method == "git":
            # Use existing git validation logic
            urls = self._collect_valid_urls()
            self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(len(urls) > 0)
        else:  # local
            # Check if local directory is valid
            directory_path = self.local_dir_input.text().strip()
            if not directory_path:
                self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
                return

            path = Path(directory_path)
            manifest_path = path / "MANIFEST.toml"
            init_path = path / "__init__.py"

            is_valid = path.exists() and path.is_dir() and manifest_path.exists() and init_path.exists()

            self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(is_valid)

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
            self._update_install_button_state()
            return

        if not non_empty:
            self._hide_feedback()
            self._update_install_button_state()
            return

        count_unique = len({t for t in non_empty})
        self._show_success_feedback(_("{count} valid URL(s) detected").format(count=count_unique))
        self._update_install_button_state()

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
        if self._current_method == "git":
            urls = self._collect_valid_urls()
            if not urls:
                return
            self._install_from_git_async(urls)
        else:  # local
            directory_path = self.local_dir_input.text().strip()
            if not directory_path:
                return
            self._install_from_local_async(directory_path)

    def _install_from_git_async(self, urls: list[str]) -> None:
        """Install plugins from git repositories asynchronously."""
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

    def _install_from_local_async(self, directory_path: str) -> None:
        """Install plugin from local directory asynchronously."""
        # Hide previous messages
        self.error_label.hide()

        # Show progress
        self._hide_local_feedback()
        # Activate progress
        self.progress_bar.setEnabled(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_label.setText(_("Installing plugin from local directory..."))
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setEnabled(False)

        # Start installation in background thread
        def install_worker():
            try:
                from picard.const.appdirs import plugin_folder
                from picard.plugin3.manager import _is_plugin_compatible
                from picard.plugin3.manifest import PluginManifest
                from picard.plugin3.plugin import PluginSourceLocal

                path = Path(directory_path)
                manifest_path = path / "MANIFEST.toml"

                # Read manifest to get plugin name and validate compatibility
                with open(manifest_path, 'rb') as manifest_file:
                    manifest = PluginManifest(path.name, manifest_file)

                plugin_name = path.name

                def progress_cb(message: str) -> None:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_update_progress",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, message),
                    )

                progress_cb("Validating plugin...")

                # Check API compatibility before installation
                if not _is_plugin_compatible(manifest.api_versions):
                    from picard import api_versions_tuple

                    error_msg = (
                        f"Plugin '{plugin_name}' is not compatible with this version of Picard. "
                        f"Plugin requires API versions: {[str(v) for v in manifest.api_versions]}, "
                        f"but Picard supports: {[str(v) for v in api_versions_tuple]}"
                    )
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_installation_failed",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, error_msg),
                    )
                    return

                # Create plugin source and copy to plugins directory
                source = PluginSourceLocal(path)
                plugins_root = Path(plugin_folder())
                target_dir = plugins_root / plugin_name

                progress_cb("Installing plugin...")
                source.sync(target_dir)

                # Touch installation marker
                (target_dir / ".installed").touch(exist_ok=True)

                # Enable the newly installed plugin by default
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_enable_plugin_by_name",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, plugin_name),
                )

                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_installation_success",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, directory_path),
                )

                # Refresh plugin list
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_refresh_plugins_list",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

            except Exception as e:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_installation_failed",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, str(e)),
                )

        thread.run_task(install_worker)

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
                        # Enable installed plugins by default
                        for plugin_name in installed_names:
                            QtCore.QMetaObject.invokeMethod(
                                self,
                                "_enable_plugin_by_name",
                                QtCore.Qt.ConnectionType.QueuedConnection,
                                QtCore.Q_ARG(str, plugin_name),
                            )
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
    @QtCore.pyqtSlot()
    def _refresh_plugins_list(self) -> None:
        names = self._get_installed_plugin_names()
        self.plugins_model.set_plugins(names)
        enabled = set()
        with suppress(AttributeError):
            enabled = set(self._plugin_manager3.get_enabled_plugins())
        self._disabled_plugins = set(names) - enabled
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
        try:
            if name in self._disabled_plugins:
                self._plugin_manager3.enable_plugin(name)
            else:
                self._plugin_manager3.disable_plugin(name)
        except Exception as e:
            log.warning("Failed to toggle plugin %s: %s", name, e)
        self._refresh_plugins_list()

    def _uninstall_selected_plugin(self) -> None:
        name = self._selected_plugin_name()
        if not name:
            return
        # Disable and remove the plugin directory from v3 plugins folder
        with suppress(Exception):
            self._plugin_manager3.disable_plugin(name)
        try:
            import shutil

            from picard.const.appdirs import plugin_folder

            target_dir = Path(plugin_folder()) / name
            if target_dir.exists():
                shutil.rmtree(target_dir)
        except Exception as e:
            log.warning("Failed to uninstall plugin %s: %s", name, e)
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

        # Also reset local directory input
        if hasattr(self, 'local_dir_input'):
            self.local_dir_input.clear()
            self._clear_plugin_info()
            self._hide_local_feedback()

    def reject(self) -> None:  # type: ignore[override]
        """Handle Cancel: reset inputs then close the dialog."""
        self._reset_url_inputs()
        super().reject()

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

    def _get_installed_plugin_names(self) -> list[str]:
        """Return names of installed plugins based on v3 plugin directory."""
        names: list[str] = []
        with suppress(Exception):
            from picard.const.appdirs import plugin_folder

            base = Path(plugin_folder())
            if base.exists():
                for entry in base.iterdir():
                    if entry.is_dir():
                        if (entry / "__init__.py").exists() and (entry / "MANIFEST.toml").exists():
                            names.append(entry.name)
        return sorted(names)

    @QtCore.pyqtSlot(str)
    def _enable_plugin_by_name(self, plugin_name: str) -> None:
        """Enable a plugin by name using v3 manager and ensure loaded."""
        try:
            pm = self._plugin_manager3
            # Make sure manager knows this plugin; if not, add directory and load
            try:
                known = any(p.name == plugin_name for p in getattr(pm, '_plugins', []))
            except Exception:
                known = False
            if not known:
                from picard.const.appdirs import plugin_folder

                plugin_dir = Path(plugin_folder())
                with suppress(Exception):
                    plugin = pm._load_plugin(plugin_dir, plugin_name)  # type: ignore[attr-defined]
                    if plugin:
                        getattr(pm, '_plugins', []).append(plugin)
            pm.enable_plugin(plugin_name)
        except Exception as e:
            log.warning("Failed to enable plugin %s: %s", plugin_name, e)
        self._refresh_plugins_list()

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
