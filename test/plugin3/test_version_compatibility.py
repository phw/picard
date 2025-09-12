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

from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from picard import api_versions_tuple
from picard.plugin3.manager import PluginManager, _compatible_api_versions, _is_plugin_compatible
from picard.plugin3.manifest import PluginManifest
from picard.plugin3.plugin import Plugin
from picard.version import Version

import pytest


@pytest.fixture
def mock_config() -> Mock:
    """Create a mock config object for testing."""
    fake_config = Mock()
    fake_config.setting = {
        'enabled_plugins3': [],
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
def temp_plugin_dir() -> Path:
    """Create a temporary directory for plugin testing."""
    return Path(tempfile.mkdtemp())


@pytest.fixture
def mock_manifest() -> Mock:
    """Create a mock plugin manifest for testing."""
    manifest = Mock(spec=PluginManifest)
    manifest.api_versions = (Version.from_string("3.0"),)
    return manifest


@pytest.mark.parametrize(
    ("plugin_versions", "expected_compatible"),
    [
        # Compatible cases
        ((Version.from_string("3.0"),), True),
        ((Version.from_string("3.0"), Version.from_string("2.9")), True),
        ((Version.from_string("2.9"), Version.from_string("3.0")), True),
        # Incompatible cases
        ((), False),  # No versions specified
        ((Version.from_string("2.9"),), False),  # Only old version
        ((Version.from_string("4.0"),), False),  # Only future version
        ((Version.from_string("2.9"), Version.from_string("4.0")), False),  # No overlap
        # Edge cases
        (None, False),  # None versions
    ],
)
def test_is_plugin_compatible(plugin_versions, expected_compatible: bool) -> None:
    """Test plugin compatibility checking."""
    result = _is_plugin_compatible(plugin_versions)
    assert result is expected_compatible


@pytest.mark.parametrize(
    ("plugin_versions", "expected_compatible_versions"),
    [
        # Compatible cases
        ((Version.from_string("3.0"),), {Version.from_string("3.0")}),
        ((Version.from_string("3.0"), Version.from_string("2.9")), {Version.from_string("3.0")}),
        ((Version.from_string("2.9"), Version.from_string("3.0")), {Version.from_string("3.0")}),
        # Incompatible cases
        ((), set()),
        ((Version.from_string("2.9"),), set()),
        ((Version.from_string("4.0"),), set()),
        ((Version.from_string("2.9"), Version.from_string("4.0")), set()),
    ],
)
def test_compatible_api_versions(plugin_versions, expected_compatible_versions: set) -> None:
    """Test finding compatible API versions."""
    result = _compatible_api_versions(plugin_versions)
    assert result == expected_compatible_versions


def test_load_plugin_compatible_version(
    plugin_manager: PluginManager, temp_plugin_dir: Path, mock_manifest: Mock
) -> None:
    """Test loading a plugin with compatible API version."""
    plugin_name = "test_plugin"
    plugin_path = temp_plugin_dir / plugin_name
    plugin_path.mkdir()

    # Create a mock manifest file
    manifest_file = plugin_path / "MANIFEST.toml"
    manifest_file.write_text("""
name = "Test Plugin"
version = "1.0.0"
api = ["3.0"]
""")

    # Mock the plugin creation and manifest reading
    with patch('picard.plugin3.manager.Plugin') as mock_plugin_class:
        mock_plugin = Mock(spec=Plugin)
        mock_plugin.name = plugin_name
        mock_plugin.local_path = plugin_path
        mock_plugin.manifest = mock_manifest
        mock_plugin_class.return_value = mock_plugin

        # Mock the manifest reading
        with patch.object(mock_plugin, 'read_manifest'):
            result = plugin_manager._load_plugin(temp_plugin_dir, plugin_name)

    assert result is not None
    assert result.name == plugin_name


def test_load_plugin_incompatible_version(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test loading a plugin with incompatible API version."""
    plugin_name = "incompatible_plugin"
    plugin_path = temp_plugin_dir / plugin_name
    plugin_path.mkdir()

    # Create a mock manifest file with incompatible version
    manifest_file = plugin_path / "MANIFEST.toml"
    manifest_file.write_text("""
name = "Incompatible Plugin"
version = "1.0.0"
api = ["2.9"]
""")

    # Mock the plugin creation and manifest reading
    with patch('picard.plugin3.manager.Plugin') as mock_plugin_class:
        mock_plugin = Mock(spec=Plugin)
        mock_plugin.name = plugin_name
        mock_plugin.local_path = plugin_path
        mock_plugin.manifest = Mock(spec=PluginManifest)
        mock_plugin.manifest.api_versions = (Version.from_string("2.9"),)
        mock_plugin_class.return_value = mock_plugin

        # Mock the manifest reading
        with patch.object(mock_plugin, 'read_manifest'):
            with patch('picard.plugin3.manager.log') as mock_log:
                result = plugin_manager._load_plugin(temp_plugin_dir, plugin_name)

    assert result is None
    mock_log.warning.assert_called_once()
    warning_call = mock_log.warning.call_args
    assert "not compatible" in warning_call[0][0]
    assert plugin_name in warning_call[0][1]  # plugin.name is the second argument


def test_load_plugin_no_api_versions(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test loading a plugin with no API versions specified."""
    plugin_name = "no_api_plugin"
    plugin_path = temp_plugin_dir / plugin_name
    plugin_path.mkdir()

    # Create a mock manifest file without API versions
    manifest_file = plugin_path / "MANIFEST.toml"
    manifest_file.write_text("""
name = "No API Plugin"
version = "1.0.0"
""")

    # Mock the plugin creation and manifest reading
    with patch('picard.plugin3.manager.Plugin') as mock_plugin_class:
        mock_plugin = Mock(spec=Plugin)
        mock_plugin.name = plugin_name
        mock_plugin.local_path = plugin_path
        mock_plugin.manifest = Mock(spec=PluginManifest)
        mock_plugin.manifest.api_versions = ()  # No API versions
        mock_plugin_class.return_value = mock_plugin

        # Mock the manifest reading
        with patch.object(mock_plugin, 'read_manifest'):
            with patch('picard.plugin3.manager.log') as mock_log:
                result = plugin_manager._load_plugin(temp_plugin_dir, plugin_name)

    assert result is None
    mock_log.warning.assert_called_once()
    warning_call = mock_log.warning.call_args
    assert "not compatible" in warning_call[0][0]
    assert plugin_name in warning_call[0][1]  # plugin.name is the second argument


def test_load_plugin_manifest_error(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test loading a plugin with manifest reading error."""
    plugin_name = "broken_plugin"
    plugin_path = temp_plugin_dir / plugin_name
    plugin_path.mkdir()

    # Mock the plugin creation
    with patch('picard.plugin3.manager.Plugin') as mock_plugin_class:
        mock_plugin = Mock(spec=Plugin)
        mock_plugin.name = plugin_name
        mock_plugin.local_path = plugin_path
        mock_plugin_class.return_value = mock_plugin

        # Mock the manifest reading to raise an exception
        with patch.object(mock_plugin, 'read_manifest', side_effect=OSError("File not found")):
            with patch('picard.plugin3.manager.log') as mock_log:
                result = plugin_manager._load_plugin(temp_plugin_dir, plugin_name)

    assert result is None
    mock_log.warning.assert_called_once()
    warning_call = mock_log.warning.call_args[0]
    assert "Could not read plugin manifest" in warning_call[0]


@pytest.mark.parametrize(
    ("api_versions", "expected_log_level", "expected_message_part"),
    [
        ((Version.from_string("3.0"),), "debug", "is compatible"),
        ((Version.from_string("2.9"),), "warning", "not compatible"),
        ((), "warning", "not compatible"),
    ],
)
def test_version_compatibility_logging(
    plugin_manager: PluginManager,
    temp_plugin_dir: Path,
    api_versions: tuple,
    expected_log_level: str,
    expected_message_part: str,
) -> None:
    """Test that version compatibility is properly logged."""
    plugin_name = "logging_test_plugin"
    plugin_path = temp_plugin_dir / plugin_name
    plugin_path.mkdir()

    # Mock the plugin creation and manifest reading
    with patch('picard.plugin3.manager.Plugin') as mock_plugin_class:
        mock_plugin = Mock(spec=Plugin)
        mock_plugin.name = plugin_name
        mock_plugin.local_path = plugin_path
        mock_plugin.manifest = Mock(spec=PluginManifest)
        mock_plugin.manifest.api_versions = api_versions
        mock_plugin_class.return_value = mock_plugin

        # Mock the manifest reading
        with patch.object(mock_plugin, 'read_manifest'):
            with patch('picard.plugin3.manager.log') as mock_log:
                plugin_manager._load_plugin(temp_plugin_dir, plugin_name)

    # Check that the appropriate log method was called
    log_method = getattr(mock_log, expected_log_level)
    log_method.assert_called()

    # Check that the log message contains the expected part
    log_calls = log_method.call_args_list
    found_expected_message = any(expected_message_part in str(call) for call in log_calls)
    assert found_expected_message


def test_api_versions_tuple_import() -> None:
    """Test that api_versions_tuple is properly imported and accessible."""
    assert api_versions_tuple is not None
    assert len(api_versions_tuple) > 0
    assert all(isinstance(v, Version) for v in api_versions_tuple)


def test_version_compatibility_edge_cases() -> None:
    """Test edge cases in version compatibility."""
    # Test with None input
    assert _is_plugin_compatible(None) is False

    # Test with empty tuple
    assert _is_plugin_compatible(()) is False

    # Test with single compatible version
    compatible_version = api_versions_tuple[0] if api_versions_tuple else Version.from_string("3.0")
    assert _is_plugin_compatible((compatible_version,)) is True

    # Test with mixed compatible and incompatible versions
    if api_versions_tuple:
        compatible_version = api_versions_tuple[0]
        incompatible_version = Version.from_string("99.0")
        assert _is_plugin_compatible((compatible_version, incompatible_version)) is True
