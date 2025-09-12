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

from __future__ import annotations

import os

from PyQt6.QtWidgets import QApplication

import pytest


@pytest.fixture(scope="session", autouse=True)
def ensure_qapplication_session() -> QApplication:
    """Ensure a QApplication exists for the entire test session.

    Some tests may otherwise create only a QCoreApplication, which would
    cause widget construction (e.g., QDialog) to abort. Creating the GUI
    application upfront avoids that class of crashes in combined runs.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(scope="session", autouse=True)
def register_options() -> None:
    """Import options to register all Option defaults once per session."""
    # Import has side effects registering all options
    import picard.options  # noqa: F401


@pytest.fixture(autouse=True)
def ensure_default_settings() -> None:
    """Ensure core default config keys exist for tests not using PicardTestCase.

    Some modules access `get_config().setting[...]` directly (e.g. extension
    points). In the full application lifecycle options are registered during
    import, but in isolated tests we emulate the minimal keys we need.
    """
    try:
        from picard.config import get_config
    except ImportError:
        return

    cfg = get_config()
    if not cfg:
        return
    # Create missing dicts like PicardTestCase.init_config does
    if not hasattr(cfg, 'setting') or cfg.setting is None:
        cfg.setting = {}
    if not hasattr(cfg, 'persist') or cfg.persist is None:
        cfg.persist = {}
    if not hasattr(cfg, 'profiles') or cfg.profiles is None:
        cfg.profiles = {}

    # Ensure plugin enablement settings exist
    if 'enabled_plugins' not in cfg.setting:
        cfg.setting['enabled_plugins'] = []
    if 'enabled_plugins3' not in cfg.setting:
        cfg.setting['enabled_plugins3'] = []


@pytest.fixture(autouse=True)
def mock_tagger_instance(monkeypatch) -> None:
    """Provide a minimal `Tagger.instance()` for widgets relying on it.

    The plugin installation dialog expects `Tagger.instance().pluginmanager3`.
    We provide a lightweight fake with the required API so tests can
    construct the dialog without spinning up the full application.
    """
    try:
        from picard.tagger import Tagger
    except Exception:  # pragma: no cover - if import fails, nothing to patch
        return

    class _FakePluginManager3:
        def get_enabled_plugins(self) -> list[str]:
            return []

        def enable_plugin(self, _name: str) -> None:
            return None

        def disable_plugin(self, _name: str) -> None:
            return None

    class _FakeTagger:
        def __init__(self) -> None:
            self.pluginmanager3 = _FakePluginManager3()

    fake = _FakeTagger()
    monkeypatch.setattr(Tagger, 'instance', staticmethod(lambda: fake))
