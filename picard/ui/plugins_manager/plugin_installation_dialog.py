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

from pathlib import Path

from PyQt6 import (  # type: ignore[import-not-found]
    QtCore,
    QtWidgets,
)

from picard import log
from picard.i18n import gettext as _
from picard.plugin3.installer import PluginInstallationError
from picard.tagger import Tagger
from picard.util import thread

from picard.ui import PicardDialog, SingletonDialog
from picard.ui.plugins_manager.config import DialogConfig
from picard.ui.plugins_manager.git_install_tab import GitInstallTab
from picard.ui.plugins_manager.install_coordinator import InstallCoordinator
from picard.ui.plugins_manager.list_components import (
    PluginItemDelegate,
    PluginListModel,
    get_installed_plugins_with_labels,
)
from picard.ui.plugins_manager.local_install_tab import LocalInstallTab
from picard.ui.plugins_manager.plugin_list_manager import PluginListManager
from picard.ui.plugins_manager.protocols import PluginManagerProtocol
from picard.ui.plugins_manager.services import InstallerService
from picard.ui.plugins_manager.validation import UrlValidator


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
        plugin_manager: PluginManagerProtocol | None = None,
    ):
        super().__init__(parent=parent)
        self.setWindowTitle(_("Install Plugin"))
        self.setModal(True)
        self.resize(DialogConfig.DEFAULT_WIDTH, DialogConfig.DEFAULT_HEIGHT)

        # Services (injected for testability)
        self._url_validator = validator or UrlValidator()
        self._installer = installer or InstallerService()
        self._coordinator = InstallCoordinator(self._installer)

        # Plugin manager (injected for testability)
        self._plugin_manager3: PluginManagerProtocol = plugin_manager or Tagger.instance().pluginmanager3

        # Coordinator-managed source; no need for separate current method

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
        # Initialize plugin list manager
        self._list_manager = PluginListManager(self.plugins_view, self.plugins_model, self._plugin_manager3)
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

        # Coordinator source defaults to Git tab
        if hasattr(self, "_git_tab"):
            self._coordinator.set_source(self._git_tab)

    def _setup_git_tab(self):
        """Set up the git repository installation tab."""
        self._git_tab = GitInstallTab(self, validator=self._url_validator)
        # Back-compat: expose inner inputs for tests referencing repo_inputs
        self.repo_inputs = self._git_tab._inputs  # type: ignore[attr-defined]
        self._git_tab.on_change(lambda: (self._reset_progress_ui(), self._update_install_button_state()))
        self.tab_widget.addTab(self._git_tab.widget(), _("From Git Repository"))

    def _setup_local_tab(self):
        """Set up the local directory installation tab."""
        self._local_tab = LocalInstallTab(self)
        # Bridge internal widgets for existing tests while logic lives in tab
        self.local_dir_input = self._local_tab.local_dir_input
        self.local_feedback = self._local_tab.local_feedback
        self.local_feedback_container = self._local_tab.local_feedback_container
        self.plugin_info_group = self._local_tab.plugin_info_group
        self.plugin_info_text = self._local_tab.plugin_info_text
        # Wire ready-state changes to button updates
        self._local_tab.on_change(lambda: self._update_install_button_state())
        self.tab_widget.addTab(self._local_tab.widget(), _("From Local Directory"))

    def _connect_signals(self):
        """Connect UI signals."""
        # Install triggers installation; Close closes dialog
        self.install_button.clicked.connect(self._start_installation)
        self.close_button.clicked.connect(self.reject)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change and update coordinator source and button state."""
        if index == 0 and hasattr(self, "_git_tab"):
            self._coordinator.set_source(self._git_tab)
        elif hasattr(self, "_local_tab"):
            self._coordinator.set_source(self._local_tab)
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

    def _update_install_button_state(self) -> None:
        """Update the install button state based on current method and validation."""
        # Use coordinator readiness to toggle button
        self.install_button.setEnabled(self._coordinator.is_ready())

    def _validate_urls(self) -> None:
        """Validate all entered URLs, de-duplicate, and update the UI feedback."""
        # Any input change should reset progress UI and delegate to tab
        self._reset_progress_ui()
        if hasattr(self, "_git_tab"):
            self._git_tab.validate()
        self._update_install_button_state()

    # Legacy single-URL validator preserved for test compatibility
    def _validate_url(self, url: str) -> None:
        url = url.strip()
        if hasattr(self, "_git_tab"):
            self._git_tab.set_first_url(url)
        self._validate_urls()

    def _is_valid_git_url(self, url: str) -> bool:
        """Check if the URL is a valid git repository URL."""
        return self._url_validator.is_valid_git_url(url)

    def _show_error_feedback(self, message: str) -> None:
        """Show error feedback message."""
        if hasattr(self, "_git_tab"):
            self._git_tab.show_error_feedback(message)

    def _show_success_feedback(self, message: str) -> None:
        """Show success feedback message."""
        if hasattr(self, "_git_tab"):
            self._git_tab.show_success_feedback(message)

    def _hide_feedback(self) -> None:
        """Hide URL feedback message."""
        if hasattr(self, "_git_tab"):
            self._git_tab.hide_feedback()

    def _start_installation(self) -> None:
        """Start the plugin installation process using the coordinator."""
        if not self._coordinator.is_ready():
            return

        # Hide previous messages and feedback
        self.error_label.hide()
        self._hide_feedback()
        self._hide_local_feedback()

        # Activate progress
        self.progress_bar.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self.progress_label.setText(_("Starting installation..."))
        self.install_button.setEnabled(False)

        def install_worker():
            try:

                def progress_cb(message: str) -> None:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_update_progress",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, message),
                    )

                installed_names, error_count = self._coordinator.install(progress_cb)

                for name in installed_names:
                    QtCore.QMetaObject.invokeMethod(
                        self,
                        "_enable_plugin_by_name",
                        QtCore.Qt.ConnectionType.QueuedConnection,
                        QtCore.Q_ARG(str, name),
                    )

                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_refresh_plugins_list",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_installation_complete",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(int, len(installed_names)),
                    QtCore.Q_ARG(int, error_count),
                )
            except (PluginInstallationError, OSError, ValueError) as e:
                QtCore.QMetaObject.invokeMethod(
                    self,
                    "_installation_failed",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, str(e)),
                )

        thread.run_task(install_worker)

    @QtCore.pyqtSlot(str)
    def _update_progress(self, message: str) -> None:
        """Update progress message."""
        self.progress_label.setText(message)

    # Backward-compat shims for local feedback and plugin info now handled in LocalInstallTab
    def _hide_local_feedback(self) -> None:
        if hasattr(self, 'local_feedback'):
            self.local_feedback.clear_and_hide()

    def _clear_plugin_info(self) -> None:
        if hasattr(self, 'plugin_info_text'):
            self.plugin_info_text.clear()

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
        self._list_manager.refresh(preserve_selection=True)
        self._update_plugin_action_buttons()

    def _selected_plugin_name(self) -> str | None:
        return self._list_manager.selected_slug()

    def _on_plugin_selection_changed(self) -> None:
        self._update_plugin_action_buttons()

    def _update_plugin_action_buttons(self) -> None:
        self._list_manager.update_action_buttons(self.toggle_button, self.uninstall_button)

    def _toggle_selected_plugin(self) -> None:
        self._list_manager.toggle_selected()

    def _uninstall_selected_plugin(self) -> None:
        self._list_manager.uninstall_selected()

    def _reset_url_inputs(self) -> None:
        """Reset URL inputs to a single empty row and refresh UI state."""
        self.repo_inputs.reset()

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
        # Delegate to shared helper to avoid duplication
        return get_installed_plugins_with_labels()

    @QtCore.pyqtSlot(str)
    def _enable_plugin_by_name(self, plugin_name: str) -> None:
        """Enable a plugin by name and refresh via the list manager."""
        self._list_manager.enable_by_name(plugin_name)

    def _collect_valid_urls(self) -> list[str]:
        """Collect and return unique valid URLs in input order."""
        if hasattr(self, "_git_tab"):
            return self._git_tab.valid_urls()
        return []
