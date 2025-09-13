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
from unittest.mock import Mock

from picard.plugin3.manager import PluginManager

import pytest


@pytest.fixture
def temp_plugin_dir() -> Path:
    """Create a temporary directory for multi-plugin repository testing."""
    return Path(tempfile.mkdtemp())


@pytest.fixture
def mock_tagger() -> Mock:
    """Create a mock tagger for testing."""
    return Mock()


@pytest.fixture
def plugin_manager(mock_tagger: Mock) -> PluginManager:
    """Create a PluginManager instance for testing."""
    manager = PluginManager(mock_tagger)
    # Clear any existing plugins to ensure clean state
    manager._plugins.clear()
    return manager


def create_mock_plugin_structure(plugin_dir: Path, plugin_name: str) -> None:
    """Create a mock plugin directory structure."""
    plugin_path = plugin_dir / plugin_name
    plugin_path.mkdir()

    # Create __init__.py
    (plugin_path / "__init__.py").write_text("""
def enable(api):
    pass

def disable():
    pass
""")

    # Create MANIFEST.toml
    (plugin_path / "MANIFEST.toml").write_text(f"""
name.en = "{plugin_name.title()} Plugin"
author = ["Test Author"]
description.en = "A test plugin for {plugin_name}"
api = ["3.0"]
license = "GPL-2.0-or-later"
""")


def test_single_plugin_repository_discovery(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that single plugin repositories are discovered correctly."""
    # Create a single plugin
    create_mock_plugin_structure(temp_plugin_dir, "single_plugin")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that the plugin was discovered
    assert len(plugin_manager._plugins) == 1
    assert plugin_manager._plugins[0].name == "single_plugin"
    assert plugin_manager._plugins[0].local_path == temp_plugin_dir / "single_plugin"


def test_multi_plugin_repository_discovery(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that multi-plugin repositories are discovered correctly."""
    # Create multiple plugins
    create_mock_plugin_structure(temp_plugin_dir, "acousticid_plugin")
    create_mock_plugin_structure(temp_plugin_dir, "lastfm_plugin")
    create_mock_plugin_structure(temp_plugin_dir, "discogs_plugin")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that all plugins were discovered
    assert len(plugin_manager._plugins) == 3

    plugin_names = {plugin.name for plugin in plugin_manager._plugins}
    expected_names = {"acousticid_plugin", "lastfm_plugin", "discogs_plugin"}
    assert plugin_names == expected_names

    # Check that each plugin has the correct path
    for plugin in plugin_manager._plugins:
        assert plugin.local_path == temp_plugin_dir / plugin.name


def test_mixed_content_repository_discovery(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that repositories with mixed content (plugins and non-plugins) work correctly."""
    # Create valid plugins
    create_mock_plugin_structure(temp_plugin_dir, "valid_plugin1")
    create_mock_plugin_structure(temp_plugin_dir, "valid_plugin2")

    # Create non-plugin directories (should be ignored)
    (temp_plugin_dir / "docs").mkdir()
    (temp_plugin_dir / "docs" / "README.md").write_text("# Documentation")

    (temp_plugin_dir / "tests").mkdir()
    (temp_plugin_dir / "tests" / "test_plugin.py").write_text("# Tests")

    # Create invalid plugin (missing MANIFEST.toml)
    (temp_plugin_dir / "invalid_plugin").mkdir()
    (temp_plugin_dir / "invalid_plugin" / "__init__.py").write_text("# No manifest")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that only valid plugins were discovered
    assert len(plugin_manager._plugins) == 2

    plugin_names = {plugin.name for plugin in plugin_manager._plugins}
    expected_names = {"valid_plugin1", "valid_plugin2"}
    assert plugin_names == expected_names


def test_plugin_discovery_with_shared_resources(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that repositories with shared resources work correctly."""
    # Create shared resources directory (should be ignored)
    shared_dir = temp_plugin_dir / "shared"
    shared_dir.mkdir()
    (shared_dir / "__init__.py").write_text("# Shared utilities")
    (shared_dir / "common_utils.py").write_text("# Common functions")

    # Create plugins
    create_mock_plugin_structure(temp_plugin_dir, "plugin1")
    create_mock_plugin_structure(temp_plugin_dir, "plugin2")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that only plugins were discovered (shared directory ignored)
    assert len(plugin_manager._plugins) == 2

    plugin_names = {plugin.name for plugin in plugin_manager._plugins}
    expected_names = {"plugin1", "plugin2"}
    assert plugin_names == expected_names


def test_plugin_discovery_with_files(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that repositories with files (not directories) work correctly."""
    # Create plugins
    create_mock_plugin_structure(temp_plugin_dir, "plugin1")
    create_mock_plugin_structure(temp_plugin_dir, "plugin2")

    # Create files (should be ignored)
    (temp_plugin_dir / "README.md").write_text("# Repository README")
    (temp_plugin_dir / ".gitignore").write_text("*.pyc")
    (temp_plugin_dir / "setup.py").write_text("# Setup script")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that only plugins were discovered
    assert len(plugin_manager._plugins) == 2

    plugin_names = {plugin.name for plugin in plugin_manager._plugins}
    expected_names = {"plugin1", "plugin2"}
    assert plugin_names == expected_names


def test_empty_repository_discovery(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that empty repositories are handled correctly."""
    # Add empty directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that no plugins were discovered
    assert len(plugin_manager._plugins) == 0


def test_plugin_discovery_with_nested_structure(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that repositories with nested structures work correctly."""
    # Create plugins at root level
    create_mock_plugin_structure(temp_plugin_dir, "root_plugin")

    # Create nested directories (should be ignored)
    nested_dir = temp_plugin_dir / "nested"
    nested_dir.mkdir()
    create_mock_plugin_structure(nested_dir, "nested_plugin")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that only root-level plugins were discovered
    assert len(plugin_manager._plugins) == 1
    assert plugin_manager._plugins[0].name == "root_plugin"


def test_plugin_discovery_with_special_characters(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that plugins with special characters in names work correctly."""
    # Create plugins with special characters
    create_mock_plugin_structure(temp_plugin_dir, "plugin_with_underscores")
    create_mock_plugin_structure(temp_plugin_dir, "plugin-with-dashes")
    create_mock_plugin_structure(temp_plugin_dir, "plugin123")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that all plugins were discovered
    assert len(plugin_manager._plugins) == 3

    plugin_names = {plugin.name for plugin in plugin_manager._plugins}
    expected_names = {"plugin_with_underscores", "plugin-with-dashes", "plugin123"}
    assert plugin_names == expected_names


def test_plugin_discovery_with_hidden_directories(plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
    """Test that hidden directories are handled correctly."""
    # Create plugins
    create_mock_plugin_structure(temp_plugin_dir, "visible_plugin")

    # Create hidden directories (currently treated as plugins if they have valid manifests)
    hidden_dir = temp_plugin_dir / ".hidden"
    hidden_dir.mkdir()
    (hidden_dir / "__init__.py").write_text("# Hidden plugin")
    (hidden_dir / "MANIFEST.toml").write_text("""
name.en = "Hidden Plugin"
author = ["Test Author"]
description.en = "A hidden plugin"
api = ["3.0"]
license = "GPL-2.0-or-later"
""")

    # Add the directory
    plugin_manager.add_directory(str(temp_plugin_dir))

    # Check that both visible and hidden plugins were discovered
    # (current behavior treats all directories as potential plugins)
    assert len(plugin_manager._plugins) == 2

    plugin_names = {plugin.name for plugin in plugin_manager._plugins}
    expected_names = {"visible_plugin", ".hidden"}
    assert plugin_names == expected_names
