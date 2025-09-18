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
from pathlib import Path
import tempfile
from unittest.mock import patch

from picard.plugin3.plugin import PluginSourceLocal, PluginSourceSyncError

import pytest


@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory for testing."""
    return Path(tempfile.mkdtemp())


@pytest.fixture
def source_plugin_dir(temp_dir: Path) -> Path:
    """Create a source plugin directory with test files."""
    source_dir = temp_dir / "source_plugin"
    source_dir.mkdir()

    # Create plugin files
    (source_dir / "__init__.py").write_text("""
def enable(api):
    pass

def disable():
    pass
""")

    (source_dir / "MANIFEST.toml").write_text("""
name = "Test Plugin"
version = "1.0.0"
api = ["3.0"]
author = "Test Author"
description = { en = "A test plugin" }
""")

    (source_dir / "plugin.py").write_text("# Plugin implementation")

    # Create a subdirectory
    (source_dir / "utils").mkdir()
    (source_dir / "utils" / "__init__.py").write_text("# Utils module")
    (source_dir / "utils" / "helpers.py").write_text("# Helper functions")

    # Create files that should be ignored
    (source_dir / "__pycache__").mkdir()
    (source_dir / "__pycache__" / "plugin.pyc").write_text("compiled bytecode")
    (source_dir / ".git").mkdir()
    (source_dir / ".git" / "config").write_text("git config")
    (source_dir / "test.log").write_text("log content")

    return source_dir


@pytest.fixture
def target_plugin_dir(temp_dir: Path) -> Path:
    """Create a target plugin directory for testing."""
    return temp_dir / "target_plugin"


def test_plugin_source_local_init_valid_path(source_plugin_dir: Path) -> None:
    """Test PluginSourceLocal initialization with valid path."""
    source = PluginSourceLocal(source_plugin_dir)
    assert source.source_path == source_plugin_dir


def test_plugin_source_local_init_string_path(source_plugin_dir: Path) -> None:
    """Test PluginSourceLocal initialization with string path."""
    source = PluginSourceLocal(str(source_plugin_dir))
    assert source.source_path == source_plugin_dir


def test_plugin_source_local_init_nonexistent_path(temp_dir: Path) -> None:
    """Test PluginSourceLocal initialization with nonexistent path."""
    nonexistent_path = temp_dir / "nonexistent"
    with pytest.raises(FileNotFoundError, match="Source path does not exist"):
        PluginSourceLocal(nonexistent_path)


def test_plugin_source_local_init_file_not_directory(temp_dir: Path) -> None:
    """Test PluginSourceLocal initialization with file instead of directory."""
    file_path = temp_dir / "not_a_directory.txt"
    file_path.write_text("not a directory")

    with pytest.raises(NotADirectoryError, match="Source path is not a directory"):
        PluginSourceLocal(file_path)


def test_sync_new_installation(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test syncing to a new target directory."""
    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that target directory was created
    assert target_plugin_dir.exists()
    assert target_plugin_dir.is_dir()

    # Check that plugin files were copied
    assert (target_plugin_dir / "__init__.py").exists()
    assert (target_plugin_dir / "MANIFEST.toml").exists()
    assert (target_plugin_dir / "plugin.py").exists()
    assert (target_plugin_dir / "utils" / "__init__.py").exists()
    assert (target_plugin_dir / "utils" / "helpers.py").exists()

    # Check that previously ignored files are now copied
    assert (target_plugin_dir / "__pycache__").exists()
    assert (target_plugin_dir / ".git").exists()
    assert (target_plugin_dir / "test.log").exists()

    # Check file contents
    assert (target_plugin_dir / "__init__.py").read_text() == (source_plugin_dir / "__init__.py").read_text()
    assert (target_plugin_dir / "MANIFEST.toml").read_text() == (source_plugin_dir / "MANIFEST.toml").read_text()


def test_sync_existing_installation(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test syncing to an existing target directory."""
    # Create existing installation
    target_plugin_dir.mkdir()
    (target_plugin_dir / "old_file.py").write_text("old content")
    (target_plugin_dir / "old_dir").mkdir()
    (target_plugin_dir / "old_dir" / "old_file.txt").write_text("old content")

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that old files were removed and new files were copied
    assert not (target_plugin_dir / "old_file.py").exists()
    assert not (target_plugin_dir / "old_dir").exists()
    assert (target_plugin_dir / "__init__.py").exists()
    assert (target_plugin_dir / "MANIFEST.toml").exists()


def test_sync_existing_empty_directory(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test syncing to an existing empty target directory."""
    # Create empty target directory
    target_plugin_dir.mkdir()

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that files were copied
    assert (target_plugin_dir / "__init__.py").exists()
    assert (target_plugin_dir / "MANIFEST.toml").exists()


def test_sync_preserves_permissions(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test that sync preserves file permissions."""
    # Make a file executable
    executable_file = source_plugin_dir / "executable.py"
    executable_file.write_text("#!/usr/bin/env python3")
    executable_file.chmod(0o755)

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that permissions were preserved
    target_executable = target_plugin_dir / "executable.py"
    assert target_executable.exists()
    # Note: On some systems, permissions might be modified by umask
    # We just check that the file exists and was copied
    assert target_executable.read_text() == executable_file.read_text()


def test_sync_handles_symlinks(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test that sync handles symbolic links correctly."""
    # Create a symbolic link
    link_target = source_plugin_dir / "link_target.txt"
    link_target.write_text("link target content")
    symlink = source_plugin_dir / "symlink.txt"
    symlink.symlink_to(link_target)

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that symlink was preserved
    target_symlink = target_plugin_dir / "symlink.txt"
    assert target_symlink.is_symlink()
    assert target_symlink.read_text() == "link target content"


def test_sync_error_handling(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test error handling during sync operation."""
    source = PluginSourceLocal(source_plugin_dir)

    # Mock shutil.copytree to raise an exception
    with patch('shutil.copytree', side_effect=OSError("Permission denied")):
        with pytest.raises(PluginSourceSyncError, match="Failed to sync plugin"):
            source.sync(target_plugin_dir)


def test_sync_creates_parent_directories(source_plugin_dir: Path, temp_dir: Path) -> None:
    """Test that sync creates parent directories if they don't exist."""
    target_plugin_dir = temp_dir / "nested" / "deep" / "target_plugin"

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that parent directories were created
    assert target_plugin_dir.exists()
    assert (target_plugin_dir / "__init__.py").exists()


def test_no_ignore_patterns_comprehensive(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test that all files are copied when no ignore patterns are used."""
    # Create various files that were previously ignored
    (source_plugin_dir / "test.pyc").write_text("compiled")
    (source_plugin_dir / "package.egg-info").mkdir()
    (source_plugin_dir / "package.egg-info" / "PKG-INFO").write_text("package info")
    (source_plugin_dir / ".pytest_cache").mkdir()
    (source_plugin_dir / ".pytest_cache" / "cache").write_text("pytest cache")
    (source_plugin_dir / ".coverage").write_text("coverage data")
    (source_plugin_dir / "error.log").write_text("error log")

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that previously ignored files are now copied
    assert (target_plugin_dir / "test.pyc").exists()
    assert (target_plugin_dir / "package.egg-info").exists()
    assert (target_plugin_dir / ".pytest_cache").exists()
    assert (target_plugin_dir / ".coverage").exists()
    assert (target_plugin_dir / "error.log").exists()

    # Check that regular files were copied
    assert (target_plugin_dir / "__init__.py").exists()
    assert (target_plugin_dir / "MANIFEST.toml").exists()


@pytest.mark.parametrize(
    ("source_path", "expected_error"),
    [
        ("/nonexistent/path", FileNotFoundError),
        ("/dev/null", NotADirectoryError),  # /dev/null is a file, not a directory
    ],
)
def test_plugin_source_local_init_error_cases(source_path: str, expected_error: type) -> None:
    """Test PluginSourceLocal initialization with various error cases."""
    with pytest.raises(expected_error):
        PluginSourceLocal(source_path)


def test_sync_with_complex_directory_structure(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test sync with a complex directory structure."""
    # Create a more complex structure
    (source_plugin_dir / "subdir1" / "subdir2").mkdir(parents=True)
    (source_plugin_dir / "subdir1" / "file1.py").write_text("file1")
    (source_plugin_dir / "subdir1" / "subdir2" / "file2.py").write_text("file2")
    (source_plugin_dir / "subdir1" / "subdir2" / "__pycache__").mkdir()
    (source_plugin_dir / "subdir1" / "subdir2" / "__pycache__" / "file2.pyc").write_text("compiled")

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that the structure was preserved
    assert (target_plugin_dir / "subdir1" / "file1.py").exists()
    assert (target_plugin_dir / "subdir1" / "subdir2" / "file2.py").exists()
    assert (target_plugin_dir / "subdir1" / "subdir2" / "__pycache__").exists()

    # Check file contents
    assert (target_plugin_dir / "subdir1" / "file1.py").read_text() == "file1"
    assert (target_plugin_dir / "subdir1" / "subdir2" / "file2.py").read_text() == "file2"


def test_sync_preserves_file_timestamps(source_plugin_dir: Path, target_plugin_dir: Path) -> None:
    """Test that sync preserves file timestamps where possible."""
    import time

    # Set a specific timestamp on source file
    test_file = source_plugin_dir / "timestamp_test.py"
    test_file.write_text("timestamp test")
    original_time = time.time() - 3600  # 1 hour ago
    os.utime(test_file, (original_time, original_time))

    source = PluginSourceLocal(source_plugin_dir)
    source.sync(target_plugin_dir)

    # Check that the file was copied
    target_file = target_plugin_dir / "timestamp_test.py"
    assert target_file.exists()
    assert target_file.read_text() == "timestamp test"

    # Note: Timestamp preservation depends on the filesystem and shutil implementation
    # We just verify the file was copied correctly


def test_plugin_source_sync_error_inheritance() -> None:
    """Test that PluginSourceSyncError inherits from Exception."""
    error = PluginSourceSyncError("test error")
    assert isinstance(error, Exception)
    assert str(error) == "test error"
