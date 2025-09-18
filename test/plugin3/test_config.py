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

from unittest.mock import Mock, patch

from picard.plugin3.manager import PluginManager

import pytest


@pytest.fixture
def mock_config() -> Mock:
    """Create a mock config object for testing."""
    fake_config = Mock()
    fake_config.setting = {
        'enabled_plugins': [],
    }
    fake_config.persist = {}
    fake_config.profiles = {}
    return fake_config


@pytest.fixture
def plugin_manager(mock_config: Mock) -> PluginManager:
    """Create a PluginManager instance for testing."""
    tagger = Mock()
    manager = PluginManager(tagger)
    manager._config = mock_config
    return manager


@pytest.fixture
def mock_plugin() -> Mock:
    """Create a mock plugin for testing."""
    plugin = Mock()
    plugin.name = 'test_plugin'
    plugin._module = None
    return plugin


def test_get_enabled_plugins_empty(plugin_manager: PluginManager) -> None:
    """Test getting enabled plugins when none are configured."""
    enabled = plugin_manager.get_enabled_plugins()
    assert enabled == []


def test_get_enabled_plugins_with_plugins(plugin_manager: PluginManager, mock_config: Mock) -> None:
    """Test getting enabled plugins when some are configured."""
    mock_config.setting['enabled_plugins'] = ['plugin1', 'plugin2']
    enabled = plugin_manager.get_enabled_plugins()
    assert enabled == ['plugin1', 'plugin2']


@pytest.mark.parametrize(
    ("plugin_name", "expected_enabled"),
    [
        ('test_plugin', True),
        ('another_plugin', True),
    ],
)
def test_set_plugin_enabled_enable(
    plugin_manager: PluginManager, mock_config: Mock, plugin_name: str, expected_enabled: bool
) -> None:
    """Test enabling a plugin."""
    # Initially no plugins enabled
    assert plugin_manager.get_enabled_plugins() == []

    # Enable a plugin
    plugin_manager.set_plugin_enabled(plugin_name, True)

    # Check it's enabled
    enabled = plugin_manager.get_enabled_plugins()
    assert plugin_name in enabled
    assert mock_config.setting['enabled_plugins'] == [plugin_name]


def test_set_plugin_enabled_disable(plugin_manager: PluginManager, mock_config: Mock) -> None:
    """Test disabling a plugin."""
    # Start with plugins enabled
    mock_config.setting['enabled_plugins'] = ['plugin1', 'plugin2']

    # Disable a plugin
    plugin_manager.set_plugin_enabled('plugin1', False)

    # Check it's disabled
    enabled = plugin_manager.get_enabled_plugins()
    assert 'plugin1' not in enabled
    assert 'plugin2' in enabled
    assert mock_config.setting['enabled_plugins'] == ['plugin2']


@pytest.mark.parametrize(
    ("initial_plugins", "plugin_name", "action", "expected_result"),
    [
        (['plugin1'], 'plugin1', True, ['plugin1']),  # Already enabled
        ([], 'plugin1', False, []),  # Already disabled
    ],
)
def test_set_plugin_enabled_idempotent(
    plugin_manager: PluginManager,
    mock_config: Mock,
    initial_plugins: list[str],
    plugin_name: str,
    action: bool,
    expected_result: list[str],
) -> None:
    """Test enabling/disabling a plugin that's already in the desired state."""
    mock_config.setting['enabled_plugins'] = initial_plugins.copy()

    # Try to change state
    plugin_manager.set_plugin_enabled(plugin_name, action)

    # Should remain unchanged
    enabled = plugin_manager.get_enabled_plugins()
    assert enabled == expected_result


@pytest.mark.parametrize(
    ("enabled_plugins", "plugin_name", "expected_result"),
    [
        (['plugin1', 'plugin2'], 'plugin1', True),
        (['plugin1', 'plugin2'], 'plugin2', True),
        (['plugin1'], 'plugin2', False),
        ([], 'plugin1', False),
    ],
)
def test_is_plugin_enabled(
    plugin_manager: PluginManager,
    mock_config: Mock,
    enabled_plugins: list[str],
    plugin_name: str,
    expected_result: bool,
) -> None:
    """Test checking if a plugin is enabled."""
    mock_config.setting['enabled_plugins'] = enabled_plugins
    assert plugin_manager.is_plugin_enabled(plugin_name) is expected_result


@pytest.mark.parametrize(
    ("plugin_name", "action", "expected_log_message"),
    [
        ('nonexistent_plugin', 'enable', 'Enabled and loaded plugin %s'),
        ('nonexistent_plugin', 'disable', 'Disabled and unloaded plugin %s'),
    ],
)
@patch('picard.plugin3.manager.log')
def test_plugin_not_found(
    mock_log: Mock, plugin_manager: PluginManager, plugin_name: str, action: str, expected_log_message: str
) -> None:
    """Test enabling/disabling a plugin that doesn't exist."""
    # No plugins loaded
    plugin_manager._plugins = []

    # Try to enable/disable a plugin
    if action == 'enable':
        plugin_manager.enable_plugin(plugin_name)
        assert plugin_manager.is_plugin_enabled(plugin_name) is True
    else:
        plugin_manager.disable_plugin(plugin_name)
        assert plugin_manager.is_plugin_enabled(plugin_name) is False

    # Should log appropriate message
    mock_log.info.assert_called_with(expected_log_message, plugin_name)


@pytest.mark.parametrize(
    ("action", "expected_calls"),
    [
        ('enable', ['load_module', 'enable']),
        ('disable', ['disable']),
    ],
)
def test_plugin_with_mock_plugin(
    plugin_manager: PluginManager, mock_plugin: Mock, action: str, expected_calls: list[str]
) -> None:
    """Test enabling/disabling a plugin with a mock plugin object."""
    if action == 'disable':
        mock_plugin._module = Mock()  # Already loaded

    plugin_manager._plugins = [mock_plugin]

    # Enable/disable the plugin
    if action == 'enable':
        plugin_manager.enable_plugin('test_plugin')
        assert plugin_manager.is_plugin_enabled('test_plugin') is True
    else:
        plugin_manager.disable_plugin('test_plugin')
        assert plugin_manager.is_plugin_enabled('test_plugin') is False

    # Check appropriate methods were called
    for method_name in expected_calls:
        method = getattr(mock_plugin, method_name)
        method.assert_called_once()


@pytest.mark.parametrize(
    ("action", "exception_type", "exception_message"),
    [
        ('enable', ImportError, 'Load failed'),
        ('disable', AttributeError, 'Unload failed'),
    ],
)
def test_plugin_error_handling(
    plugin_manager: PluginManager, action: str, exception_type: type[Exception], exception_message: str
) -> None:
    """Test enabling/disabling a plugin that raises an exception."""
    # Create a mock plugin that raises an exception
    mock_plugin = Mock()
    mock_plugin.name = 'failing_plugin'
    mock_plugin._module = Mock() if action == 'disable' else None

    if action == 'enable':
        mock_plugin.load_module.side_effect = exception_type(exception_message)
    else:
        mock_plugin.disable.side_effect = exception_type(exception_message)

    plugin_manager._plugins = [mock_plugin]

    # Enable/disable the plugin (should not raise exception)
    if action == 'enable':
        plugin_manager.enable_plugin('failing_plugin')
        assert plugin_manager.is_plugin_enabled('failing_plugin') is True
    else:
        plugin_manager.disable_plugin('failing_plugin')
        assert plugin_manager.is_plugin_enabled('failing_plugin') is False


@pytest.mark.parametrize(
    ("plugin_name", "expected_result"),
    [
        ('test_plugin', True),
        ('another_plugin', True),
        ('nonexistent_plugin', False),
        ('', False),
    ],
)
def test_find_plugin_by_name(
    plugin_manager: PluginManager, mock_plugin: Mock, plugin_name: str, expected_result: bool
) -> None:
    """Test finding a plugin by name."""
    # Create additional mock plugins
    another_plugin = Mock()
    another_plugin.name = 'another_plugin'

    plugin_manager._plugins = [mock_plugin, another_plugin]

    result = plugin_manager.find_plugin_by_name(plugin_name)

    if expected_result:
        assert result is not None
        assert result.name == plugin_name
    else:
        assert result is None


def test_find_plugin_by_name_empty_plugins_list(plugin_manager: PluginManager) -> None:
    """Test finding a plugin when no plugins are loaded."""
    plugin_manager._plugins = []

    result = plugin_manager.find_plugin_by_name('any_plugin')
    assert result is None


def test_find_plugin_by_name_multiple_plugins(plugin_manager: PluginManager) -> None:
    """Test finding a plugin when multiple plugins exist."""
    # Create multiple mock plugins
    plugin1 = Mock()
    plugin1.name = 'plugin1'
    plugin2 = Mock()
    plugin2.name = 'plugin2'
    plugin3 = Mock()
    plugin3.name = 'plugin3'

    plugin_manager._plugins = [plugin1, plugin2, plugin3]

    # Test finding each plugin
    assert plugin_manager.find_plugin_by_name('plugin1') is plugin1
    assert plugin_manager.find_plugin_by_name('plugin2') is plugin2
    assert plugin_manager.find_plugin_by_name('plugin3') is plugin3

    # Test finding non-existent plugin
    assert plugin_manager.find_plugin_by_name('nonexistent') is None


def test_find_plugin_by_name_case_sensitive(plugin_manager: PluginManager, mock_plugin: Mock) -> None:
    """Test that plugin name matching is case sensitive."""
    plugin_manager._plugins = [mock_plugin]

    # Should find exact match
    assert plugin_manager.find_plugin_by_name('test_plugin') is mock_plugin

    # Should not find case variations
    assert plugin_manager.find_plugin_by_name('Test_Plugin') is None
    assert plugin_manager.find_plugin_by_name('TEST_PLUGIN') is None
    assert plugin_manager.find_plugin_by_name('test_Plugin') is None
