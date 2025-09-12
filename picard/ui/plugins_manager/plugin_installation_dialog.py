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

"""Dialog for installing plugins from git repositories or local directories."""

from contextlib import suppress
from pathlib import Path

from PyQt6 import (  # type: ignore[import-not-found]
    QtCore,
    QtWidgets,
)

from picard import log
from picard.i18n import gettext as _
from picard.plugin3.installer import ManifestValidationError, PluginDiscovery, PluginInstallationError, PluginValidator
from picard.tagger import Tagger
from picard.util import thread

from picard.ui import PicardDialog, SingletonDialog
from picard.ui.plugins_manager.config import DialogConfig
from picard.ui.plugins_manager.list_components import SLUG_ROLE, PluginItemDelegate, PluginListModel
from picard.ui.plugins_manager.manifest_info import build_manifest_info_html
from picard.ui.plugins_manager.services import InstallerService
from picard.ui.plugins_manager.validation import UrlValidator
from picard.ui.plugins_manager.widgets import FeedbackWidget


# Configuration: maximum characters to show for description previews
DESCRIPTION_PREVIEW_CHARS: int = DialogConfig.DESCRIPTION_MAX_CHARS


class PluginInstallationDialog(PicardDialog, SingletonDialog):
    """Dialog for installing plugins from git repositories or local directories."""

    # Signals
    plugin_installed = QtCore.pyqtSignal(str)  # Emitted when plugin is successfully installed
    installation_failed = QtCore.pyqtSignal(str)  # Emitted when installation fails

    def __init__(
        self,
        parent=None,
        *,
        installer: InstallerService | None = None,
        validator: UrlValidator | None = None,
        plugin_manager=None,
    ):
        super().__init__(parent=parent)
        self.setWindowTitle(_("Install Plugin"))
        self.setModal(True)
        self.resize(DialogConfig.DEFAULT_WIDTH, DialogConfig.DEFAULT_HEIGHT)

        # Services (injected for testability)
        self._url_validator = validator or UrlValidator()
        self._installer = installer or InstallerService()

        # Plugin manager (injected for testability)
        self._plugin_manager3 = plugin_manager or Tagger.instance().pluginmanager3

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
        # Do not steal focus from the list when toggling
        self.toggle_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        plugins_buttons_layout.addWidget(self.toggle_button)
        plugins_buttons_layout.addWidget(self.uninstall_button)
        left_layout.addLayout(plugins_buttons_layout)

        # Initialize plugin list
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

        # Button box: Close (neutral) and Install (action)
        self.button_box = QtWidgets.QDialogButtonBox()
        self.close_button = self.button_box.addButton(QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.install_button = self.button_box.addButton(_("Install"), QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        self.install_button.setEnabled(False)
        layout.addWidget(self.button_box)
        # Keep right pane content stuck to the top when dialog grows vertically
        layout.addStretch(1)

        # Assemble panes
        main_layout.addWidget(left_container, stretch=1)
        main_layout.addWidget(right_container, stretch=2)

        # Discovered local plugins cache (set during validation)
        self._discovered_local_plugins: list[Path] = []

        # Ensure progress UI starts in a reset state
        self._reset_progress_ui()

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
        self.max_urls = DialogConfig.MAX_URLS
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

        self.url_feedback = FeedbackWidget()
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
                "Select a local directory containing a Picard plugin or a repository with "
                "one or more plugin directories. Each plugin directory must contain "
                "a MANIFEST.toml file and follow the plugin package structure."
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

        self.local_feedback = FeedbackWidget()
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
        # Install triggers installation; Close closes dialog
        self.install_button.clicked.connect(self._start_installation)
        self.close_button.clicked.connect(self.reject)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change to update current method and button state."""
        if index == 0:  # Git tab
            self._current_method = "git"
        else:  # Local tab
            self._current_method = "local"
        # Input context changed; reset progress UI and update
        self._reset_progress_ui()
        self._update_install_button_state()

    def _reset_progress_ui(self) -> None:
        """Reset installation progress UI to initial, idle state."""
        # Reset progress bar
        self.progress_bar.setEnabled(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        # Clear progress text and errors
        self.progress_label.setText("")
        self.error_label.hide()
        # Reset install button; Close remains available
        self.install_button.setText(_("Install"))
        self.install_button.setEnabled(False)

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

        # Any input change should reset progress UI
        self._reset_progress_ui()

        if not directory_path:
            self._discovered_local_plugins = []
            self._hide_local_feedback()
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        path = Path(directory_path)

        # Check if path exists and is a directory
        if not path.exists():
            self._discovered_local_plugins = []
            self._show_local_error_feedback(_("Directory does not exist"))
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        if not path.is_dir():
            self._discovered_local_plugins = []
            self._show_local_error_feedback(_("Path is not a directory"))
            self._clear_plugin_info()
            self._update_install_button_state()
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
            self._show_local_error_feedback(_("No plugins found in directory"))
            self._clear_plugin_info()
            self._update_install_button_state()
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
            self._show_local_error_feedback(_("No compatible plugins found in directory"))
            self._clear_plugin_info()
            self._update_install_button_state()
            return

        self._discovered_local_plugins = [p for (_n, p, _m) in valid]

        # Display info: single plugin -> detailed; multiple -> summary list
        if len(valid) == 1:
            _name, plugin_path, manifest = valid[0]
            self._display_plugin_info(manifest, plugin_path)
            self._show_local_success_feedback(_("Valid plugin directory detected"))
        else:
            items = []
            for name, plugin_path, manifest in valid:
                display_name = (
                    manifest.name.get('en', next(iter(manifest.name.values())))
                    if hasattr(manifest, 'name') and isinstance(manifest.name, dict) and manifest.name
                    else str(getattr(manifest, 'name', name))
                )
                items.append(f"<li><b>{display_name}</b> <span style='color:#666'>({plugin_path.name})</span></li>")
            html = (
                f"<b>Found {len(valid)} valid plugins:</b><ul>"
                + "".join(items)
                + "</ul>"
                + (
                    f"<div style='color:#d32f2f'>{_('Some entries were invalid and will be skipped')}.</div>"
                    if invalid_errors
                    else ""
                )
            )
            self.plugin_info_text.setHtml(html)
            self._show_local_success_feedback(_("Valid plugin repository detected"))

        self._update_install_button_state()

    def _display_plugin_info(self, manifest, path: Path) -> None:
        """Display plugin information in the info text area."""
        html_text = build_manifest_info_html(manifest, path, max_chars=DESCRIPTION_PREVIEW_CHARS)
        self.plugin_info_text.setHtml(html_text)

    def _description_preview(self, manifest) -> str:
        # Backward-compat shim retained for tests that call this private method
        from picard.ui.plugins_manager.manifest_info import description_preview as _dp

        return _dp(manifest, max_chars=DESCRIPTION_PREVIEW_CHARS)

    def _clear_plugin_info(self) -> None:
        """Clear the plugin information display."""
        self.plugin_info_text.clear()

    def _show_local_error_feedback(self, message: str) -> None:
        """Show error feedback for local directory validation."""
        self.local_feedback.show_error(message)

    def _show_local_success_feedback(self, message: str) -> None:
        """Show success feedback for local directory validation."""
        self.local_feedback.show_success(message)

    def _hide_local_feedback(self) -> None:
        """Hide local directory feedback message."""
        self.local_feedback.clear_and_hide()

    def _update_install_button_state(self) -> None:
        """Update the install button state based on current method and validation."""
        if self._current_method == "git":
            # Use existing git validation logic
            urls = self._collect_valid_urls()
            self.install_button.setEnabled(len(urls) > 0)
        else:  # local
            # Enable if validation discovered at least one plugin
            is_enabled = bool(self._discovered_local_plugins)
            self.install_button.setEnabled(is_enabled)

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
        # Any input change should reset progress UI
        self._reset_progress_ui()
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
        return self._url_validator.is_valid_git_url(url)

    def _show_error_feedback(self, message: str) -> None:
        """Show error feedback message."""
        self.url_feedback.show_error(message)

    def _show_success_feedback(self, message: str) -> None:
        """Show success feedback message."""
        self.url_feedback.show_success(message)

    def _hide_feedback(self) -> None:
        """Hide URL feedback message."""
        self.url_feedback.clear_and_hide()

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
        self.install_button.setEnabled(False)

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
        self.install_button.setEnabled(False)

        # Start installation in background thread via installer service
        def install_worker():
            try:

                def progress_cb(message: str) -> None:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_update_progress",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, message),
                    )

                installed_names = self._installer.install_from_local(directory_path, progress=progress_cb)

                for name in installed_names:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_enable_plugin_by_name",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, name),
                    )

                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_installation_success",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, directory_path),
                )

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
                installer = self._installer
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

        # Disable Install after success; Close remains
        self.install_button.setEnabled(False)

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

        # Re-evaluate Install enabled state based on current inputs
        self.install_button.setText(_("Install"))
        self._update_install_button_state()

        # Emit signal
        self.installation_failed.emit(error_message)

        log.error("Plugin installation failed: %s", error_message)

    # --- Installed plugins pane logic ---
    @QtCore.pyqtSlot()
    def _refresh_plugins_list(self) -> None:
        # Preserve currently selected plugin slug to restore selection after refresh
        previously_selected_slug = self._selected_plugin_name()

        items = self._get_installed_plugins_with_labels()
        self.plugins_model.set_plugins(items)
        enabled = set()
        with suppress(AttributeError):
            enabled = set(self._plugin_manager3.get_enabled_plugins())
        self._disabled_plugins = {slug for (slug, _label) in items} - enabled
        self.plugins_model.set_disabled(self._disabled_plugins)
        # Restore selection and focus if possible
        if previously_selected_slug is not None and self.plugins_view.selectionModel():
            selection_model = self.plugins_view.selectionModel()
            for row in range(self.plugins_model.rowCount()):
                index = self.plugins_model.index(row, 0)
                slug = self.plugins_model.data(index, SLUG_ROLE)
                if slug == previously_selected_slug:
                    flags = (
                        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                        | QtCore.QItemSelectionModel.SelectionFlag.Current
                    )
                    selection_model.setCurrentIndex(index, flags)
                    # Ensure keyboard focus stays on the list view
                    self.plugins_view.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
                    break
        self._update_plugin_action_buttons()

    def _selected_plugin_name(self) -> str | None:
        indexes = self.plugins_view.selectedIndexes()
        if not indexes:
            return None
        # Return slug for operations
        return self.plugins_model.data(indexes[0], SLUG_ROLE)

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
        # Reset progress UI as context is cleared
        self._reset_progress_ui()

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
        # After completion keep Close visible and disable Install until inputs change
        self.install_button.setEnabled(False)

    def _get_installed_plugins_with_labels(self) -> list[tuple[str, str]]:
        """Return (slug, label) for installed plugins.

        Label is the human-readable name from MANIFEST.toml if available; fallback to slug.
        """
        items: list[tuple[str, str]] = []
        with suppress(Exception):
            from picard.const.appdirs import plugin_folder
            from picard.plugin3.manifest import PluginManifest

            base = Path(plugin_folder())
            if base.exists():
                for entry in base.iterdir():
                    if entry.is_dir():
                        init_ok = (entry / "__init__.py").exists()
                        mani = entry / "MANIFEST.toml"
                        if init_ok and mani.exists():
                            label = entry.name
                            with suppress(OSError, ValueError, KeyError):
                                with open(mani, 'rb') as fp:
                                    manifest = PluginManifest(entry.name, fp)
                                    raw_name = getattr(manifest, 'name', None)
                                    if isinstance(raw_name, dict) and raw_name:
                                        label = raw_name.get('en', next(iter(raw_name.values())))
                                    elif isinstance(raw_name, str) and raw_name.strip():
                                        label = raw_name.strip()
                            items.append((entry.name, label))
        # Sort by label for nicer UX
        return sorted(items, key=lambda p: p[1].lower())

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
