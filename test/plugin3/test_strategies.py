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
from unittest.mock import patch

from picard.ui.plugins_manager.strategies import GitInstallationStrategy, LocalInstallationStrategy


def test_git_strategy_calls_service() -> None:
    with patch("picard.ui.plugins_manager.strategies.PluginInstallationService") as svc_cls:
        svc = svc_cls.return_value
        svc.install_from_git.return_value = ["p1"]
        strategy = GitInstallationStrategy()
        out = strategy.install("https://example.com/x/y", progress=lambda _m: None)
        svc.install_from_git.assert_called_once()
        assert out == ["p1"]


def test_local_strategy_installs_and_touches(tmp_path: Path) -> None:
    # Prepare fake plugin directory with required files
    plugin_dir = tmp_path / "myplugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("# init")
    (plugin_dir / "MANIFEST.toml").write_text("name='x'")

    with (
        patch("picard.ui.plugins_manager.strategies.PluginDiscovery") as disc_cls,
        patch("picard.ui.plugins_manager.strategies.PluginValidator") as val_cls,
        patch("picard.ui.plugins_manager.strategies.PluginCopier") as copier_cls,
    ):
        disc = disc_cls.return_value
        val = val_cls.return_value
        copier = copier_cls.return_value

        disc.discover.return_value = [plugin_dir]
        val.validate.return_value = "myplugin"

        # Fake plugins root where files would be copied
        copier.plugins_root = tmp_path / "installed"
        copier.plugins_root.mkdir()

        strategy = LocalInstallationStrategy(copier=copier)
        out = strategy.install(str(tmp_path), progress=lambda _m: None)

        # Verify copy invoked
        assert copier.copy.call_count == 1
        assert out == ["myplugin"]
