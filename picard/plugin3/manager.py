# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2024 Philipp Wolfer
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
from pathlib import Path
from typing import List

from picard import (
    api_versions_tuple,
    log,
)
from picard.config import get_config
from picard.plugin3.plugin import Plugin


class PluginManager:
    """Installs, loads and updates plugins from multiple plugin directories."""

    _primary_plugin_dir: Path | None = None
    _plugin_dirs: List[Path] = []
    _plugins: List[Plugin] = []

    def __init__(self, tagger):
        from picard.tagger import Tagger

        self._tagger: Tagger = tagger
        self._config = get_config()

    def add_directory(self, dir_path: str, primary: bool = False) -> None:
        log.debug('Registering plugin directory %s', dir_path)
        plugin_dir = Path(os.path.normpath(dir_path))

        os.makedirs(plugin_dir, exist_ok=True)

        for entry in plugin_dir.iterdir():
            if entry.is_dir():
                plugin = self._load_plugin(plugin_dir, entry.name)
                if plugin:
                    log.debug('Found plugin %s in %s', plugin.name, plugin.local_path)
                    self._plugins.append(plugin)

        self._plugin_dirs.append(plugin_dir)
        if primary:
            self._primary_plugin_dir = plugin_dir

    def init_plugins(self):
        """Initialize and load enabled plugins."""
        enabled_plugins = self.get_enabled_plugins()
        for plugin in self._plugins:
            if plugin.name in enabled_plugins:
                try:
                    plugin.load_module()
                    plugin.enable(self._tagger)
                    log.debug('Enabled plugin %s', plugin.name)
                except (ImportError, OSError, AttributeError, TypeError):
                    log.exception('Failed initializing plugin %s from %s', plugin.name, plugin.local_path)
            else:
                log.debug('Plugin %s is disabled, skipping', plugin.name)

    def _load_plugin(self, plugin_dir: Path, plugin_name: str) -> Plugin | None:
        plugin = Plugin(plugin_dir, plugin_name)
        try:
            plugin.read_manifest()
            # Check version compatibility
            if not _is_plugin_compatible(plugin.manifest.api_versions):
                log.warning(
                    'Plugin "%s" from "%s" is not compatible with this version of Picard. '
                    'Plugin requires API versions: %s, but Picard supports: %s',
                    plugin.name,
                    plugin.local_path,
                    [str(v) for v in plugin.manifest.api_versions],
                    [str(v) for v in api_versions_tuple],
                )
                return None

            # Log compatible versions for debugging
            compatible_versions = _compatible_api_versions(plugin.manifest.api_versions)
            log.debug(
                'Plugin "%s" is compatible with Picard API versions: %s',
                plugin.name,
                [str(v) for v in compatible_versions],
            )
        except (OSError, ValueError, KeyError) as ex:
            log.warning('Could not read plugin manifest from %r', plugin_dir.joinpath(plugin_name), exc_info=ex)
            return None
        else:
            return plugin

    def get_enabled_plugins(self) -> List[str]:
        """Get list of enabled plugin names from configuration."""
        return self._config.setting['enabled_plugins']

    def set_plugin_enabled(self, plugin_name: str, enabled: bool) -> None:
        """Enable or disable a plugin."""
        enabled_plugins = self.get_enabled_plugins()
        if enabled:
            if plugin_name not in enabled_plugins:
                enabled_plugins.append(plugin_name)
                self._config.setting['enabled_plugins'] = enabled_plugins
                log.debug('Enabled plugin %s', plugin_name)
        else:
            if plugin_name in enabled_plugins:
                enabled_plugins.remove(plugin_name)
                self._config.setting['enabled_plugins'] = enabled_plugins
                log.debug('Disabled plugin %s', plugin_name)

    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is enabled."""
        return plugin_name in self.get_enabled_plugins()

    def enable_plugin(self, plugin_name: str) -> None:
        """Enable a plugin and load it if not already loaded."""
        self.set_plugin_enabled(plugin_name, True)
        # Find and load the plugin if it exists
        plugin_found = False
        for plugin in self._plugins:
            # Only load if not already loaded; `_module` is a state indicator
            # plugin._module = None means the plugin is NOT loaded (just discovered)
            # plugin._module = <module> means the plugin is loaded and ready to use
            if plugin.name == plugin_name and not getattr(plugin, '_module', None):
                plugin_found = True
                try:
                    plugin.load_module()
                    plugin.enable(self._tagger)
                    log.info('Enabled and loaded plugin %s', plugin_name)
                except (ImportError, OSError, AttributeError, TypeError):
                    log.exception('Failed to load plugin %s', plugin_name)

        if not plugin_found:
            log.info('Enabled and loaded plugin %s', plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """Disable a plugin and unload it if loaded."""
        self.set_plugin_enabled(plugin_name, False)
        # Find and unload the plugin if it exists
        plugin_found = False
        for plugin in self._plugins:
            # Only unload if already loaded
            if plugin.name == plugin_name and getattr(plugin, '_module', None):
                plugin_found = True
                try:
                    plugin.disable()
                    log.info('Disabled and unloaded plugin %s', plugin_name)
                except (AttributeError, TypeError):
                    log.exception('Failed to unload plugin %s', plugin_name)

        if not plugin_found:
            log.info('Disabled and unloaded plugin %s', plugin_name)


def _is_plugin_compatible(plugin_api_versions) -> bool:
    """Check if a plugin is compatible with the current Picard version.

    Args:
        plugin_api_versions: Tuple of Version objects that the plugin supports

    Returns:
        True if the plugin is compatible, False otherwise
    """
    if not plugin_api_versions:
        # Plugin doesn't specify API versions - assume incompatible for safety
        return False

    # Check if any of the plugin's supported API versions match Picard's supported versions
    compatible_versions = _compatible_api_versions(plugin_api_versions)
    return len(compatible_versions) > 0


def _compatible_api_versions(api_versions):
    """Find API versions that are compatible between plugin and Picard.

    Args:
        api_versions: Tuple of Version objects that the plugin supports

    Returns:
        Set of Version objects that are compatible
    """
    return set(api_versions) & set(api_versions_tuple)
