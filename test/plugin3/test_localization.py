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

from picard.i18n import P_, PN_, load_plugin_translation
from picard.plugin3.api import PluginApi
from picard.plugin3.manifest import PluginManifest

import pytest


@pytest.fixture
def mock_manifest() -> Mock:
    """Create a mock plugin manifest for testing."""
    manifest = Mock(spec=PluginManifest)
    manifest.module_name = "example_plugin"
    return manifest


@pytest.fixture
def mock_tagger() -> Mock:
    """Create a mock tagger for testing."""
    return Mock()


@pytest.fixture
def plugin_api(mock_manifest: Mock, mock_tagger: Mock) -> PluginApi:
    """Create a PluginApi instance for testing."""
    return PluginApi(mock_manifest, mock_tagger)


@pytest.fixture
def temp_locale_dir() -> Path:
    """Create a temporary directory for locale files."""
    return Path(tempfile.mkdtemp())


@pytest.mark.parametrize(
    ("message", "plugin_domain", "expected_result"),
    [
        # Basic functionality
        ("Hello", "plugin-example", "Hello"),
        ("", "plugin-example", ""),
        # With existing plugin translation
        ("Test message", "plugin-example", "Test message"),
        # With non-existent domain
        ("Hello", "plugin-nonexistent", "Hello"),
    ],
)
def test_p_function_basic(message: str, plugin_domain: str, expected_result: str) -> None:
    """Test basic P_ function functionality."""
    result = P_(message, plugin_domain)
    assert result == expected_result


def test_p_function_with_plugin_translation(temp_locale_dir: Path) -> None:
    """Test P_ function with actual plugin translation loaded."""
    # Create a mock .mo file structure
    locale_dir = temp_locale_dir / "en" / "LC_MESSAGES"
    locale_dir.mkdir(parents=True)

    # Mock the translation loading
    with patch('picard.i18n._load_translation') as mock_load:
        mock_translation = Mock()
        mock_translation.gettext.side_effect = lambda msg: "Translated: " + msg if msg == "Hello" else msg
        mock_load.return_value = mock_translation

        # Load plugin translation
        load_plugin_translation("plugin-example", str(temp_locale_dir), "en")

        # Test translation
        result = P_("Hello", "plugin-example")
        assert result == "Translated: Hello"

        # Test fallback for untranslated message
        result = P_("Goodbye", "plugin-example")
        assert result == "Goodbye"


def test_p_function_fallback_to_main_domain() -> None:
    """Test P_ function fallback to main domain."""
    # Mock the main translation
    with patch('picard.i18n._translation') as mock_translations:
        mock_main_translation = Mock()
        mock_main_translation.gettext.return_value = "Main translated"
        mock_translations.__getitem__.side_effect = lambda key: mock_main_translation if key == 'main' else None

        result = P_("Hello", "plugin-nonexistent")
        assert result == "Main translated"


@pytest.mark.parametrize(
    ("message", "plugin_domain", "expected_result"),
    [
        ("Hello", "plugin-example", "Hello"),
        ("", "plugin-example", ""),
        ("Test message", "plugin-nonexistent", "Test message"),
    ],
)
def test_pn_function(message: str, plugin_domain: str, expected_result: str) -> None:
    """Test PN_ function (no-op marker)."""
    result = PN_(message, plugin_domain)
    assert result == expected_result


def test_load_plugin_translation(temp_locale_dir: Path) -> None:
    """Test loading plugin translations."""
    with patch('picard.i18n._load_translation') as mock_load:
        mock_translation = Mock()
        mock_load.return_value = mock_translation

        load_plugin_translation("plugin-example", str(temp_locale_dir), "en")

        # Verify that _load_translation was called with correct parameters
        mock_load.assert_called_once()
        call_args = mock_load.call_args
        assert call_args[0][0] == "plugin-example"  # domain
        assert call_args[0][1] == str(temp_locale_dir)  # localedir
        assert call_args[1]["language"] == "en"


def test_load_plugin_translation_default_language(temp_locale_dir: Path) -> None:
    """Test loading plugin translations with default language."""
    with patch('picard.i18n._load_translation') as mock_load, patch('picard.i18n.locale.getlocale') as mock_getlocale:
        mock_getlocale.return_value = ("de", "UTF-8")
        mock_translation = Mock()
        mock_load.return_value = mock_translation

        load_plugin_translation("plugin-example", str(temp_locale_dir))

        # Verify that the default language was used
        call_args = mock_load.call_args
        assert call_args[1]["language"] == "de"


def test_plugin_api_translation_domain(plugin_api: PluginApi) -> None:
    """Test that PluginApi sets up correct translation domain."""
    assert plugin_api._translation_domain == "plugin-example_plugin"


def test_plugin_api_translate_method(plugin_api: PluginApi) -> None:
    """Test PluginApi translate method."""
    with patch('picard.i18n.P_') as mock_p:
        mock_p.return_value = "Translated message"

        result = plugin_api.translate("Hello")

        mock_p.assert_called_once_with("Hello", "plugin-example_plugin")
        assert result == "Translated message"


def test_plugin_api_translate_noop_method(plugin_api: PluginApi) -> None:
    """Test PluginApi translate_noop method."""
    with patch('picard.i18n.PN_') as mock_pn:
        mock_pn.return_value = "Original message"

        result = plugin_api.translate_noop("Hello")

        mock_pn.assert_called_once_with("Hello", "plugin-example_plugin")
        assert result == "Original message"


def test_plugin_api_translation_setup(plugin_api: PluginApi) -> None:
    """Test that PluginApi sets up translations during initialization."""
    # The _setup_plugin_translations method should be called during __init__
    # For now, it's a no-op, but we can verify it exists and is callable
    assert hasattr(plugin_api, '_setup_plugin_translations')
    assert callable(plugin_api._setup_plugin_translations)


@pytest.mark.parametrize(
    ("plugin_domain", "expected_domain"),
    [
        ("example", "plugin-example"),
        ("my_plugin", "plugin-my_plugin"),
        ("test-plugin", "plugin-test-plugin"),
    ],
)
def test_plugin_translation_domain_naming(plugin_domain: str, expected_domain: str) -> None:
    """Test that plugin translation domains are named correctly."""
    manifest = Mock(spec=PluginManifest)
    manifest.module_name = plugin_domain
    tagger = Mock()

    api = PluginApi(manifest, tagger)
    assert api._translation_domain == expected_domain


def test_translation_fallback_chain() -> None:
    """Test the complete translation fallback chain."""
    with patch('picard.i18n._translation') as mock_translations:
        # Mock plugin translation that doesn't have the message
        mock_plugin_translation = Mock()
        mock_plugin_translation.gettext.return_value = "Hello"  # Same as original

        # Mock main translation that has the message
        mock_main_translation = Mock()
        mock_main_translation.gettext.return_value = "Hallo"  # German translation

        def mock_getitem(key):
            if key == "plugin-example":
                return mock_plugin_translation
            elif key == "main":
                return mock_main_translation
            return None

        mock_translations.__getitem__.side_effect = mock_getitem

        # Test that it falls back to main domain
        result = P_("Hello", "plugin-example")
        assert result == "Hallo"


def test_translation_with_plugin_specific_translation() -> None:
    """Test translation when plugin has specific translation."""
    with patch('picard.i18n._translation') as mock_translations:
        # Mock plugin translation that has the message
        mock_plugin_translation = Mock()
        mock_plugin_translation.gettext.return_value = "Bonjour"  # French translation

        # Mock main translation as fallback
        mock_main_translation = Mock()
        mock_main_translation.gettext.return_value = "Hello"

        def mock_getitem(key):
            if key == "plugin-example":
                return mock_plugin_translation
            elif key == "main":
                return mock_main_translation
            return None

        def mock_contains(key):
            return key in ["plugin-example", "main"]

        mock_translations.__getitem__.side_effect = mock_getitem
        mock_translations.__contains__.side_effect = mock_contains

        # Test that it uses plugin-specific translation
        result = P_("Hello", "plugin-example")
        assert result == "Bonjour"


def test_empty_message_handling() -> None:
    """Test that empty messages are handled correctly."""
    result = P_("", "plugin-example")
    assert result == ""


def test_translation_domain_isolation() -> None:
    """Test that different plugin domains are isolated."""
    with patch('picard.i18n._translation') as mock_translations:
        # Mock different translations for different domains
        mock_plugin1_translation = Mock()
        mock_plugin1_translation.gettext.return_value = "Plugin 1 translation"

        mock_plugin2_translation = Mock()
        mock_plugin2_translation.gettext.return_value = "Plugin 2 translation"

        # Mock main translation as fallback
        mock_main_translation = Mock()
        mock_main_translation.gettext.return_value = "Hello"

        def mock_getitem(key):
            if key == "plugin-example1":
                return mock_plugin1_translation
            elif key == "plugin-example2":
                return mock_plugin2_translation
            elif key == "main":
                return mock_main_translation
            return None

        def mock_contains(key):
            return key in ["plugin-example1", "plugin-example2", "main"]

        mock_translations.__getitem__.side_effect = mock_getitem
        mock_translations.__contains__.side_effect = mock_contains

        # Test that each domain gets its own translation
        result1 = P_("Hello", "plugin-example1")
        result2 = P_("Hello", "plugin-example2")

        assert result1 == "Plugin 1 translation"
        assert result2 == "Plugin 2 translation"


def test_plugin_api_integration() -> None:
    """Test complete PluginApi integration with translations."""
    manifest = Mock(spec=PluginManifest)
    manifest.module_name = "test_plugin"
    tagger = Mock()

    api = PluginApi(manifest, tagger)

    # Test that the API is properly set up
    assert api._translation_domain == "plugin-test_plugin"
    assert hasattr(api, 'translate')
    assert hasattr(api, 'translate_noop')

    # Test that methods work
    with patch('picard.i18n.P_') as mock_p, patch('picard.i18n.PN_') as mock_pn:
        mock_p.return_value = "Translated"
        mock_pn.return_value = "Original"

        assert api.translate("Hello") == "Translated"
        assert api.translate_noop("Hello") == "Original"

        # Verify correct domain was used
        mock_p.assert_called_with("Hello", "plugin-test_plugin")
        mock_pn.assert_called_with("Hello", "plugin-test_plugin")
