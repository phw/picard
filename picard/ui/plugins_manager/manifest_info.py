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

"""Utility functions for building plugin manifest info."""

import html
from pathlib import Path


def description_preview(manifest, max_chars: int) -> str:
    """Return a single-line, truncated description from the manifest.

    Parameters
    ----------
    manifest
        Plugin manifest object with a description attribute or method.
    max_chars
        Maximum number of characters to include in preview.
    """
    raw = None
    if hasattr(manifest, 'description'):
        desc_attr = manifest.description
        if callable(desc_attr):
            try:
                raw = desc_attr('en')
            except TypeError:
                raw = desc_attr()
        else:
            value = desc_attr
            if isinstance(value, dict) and value:
                raw = value.get('en', next(iter(value.values())))
            else:
                raw = str(value)
    if not raw:
        return ""
    normalized = " ".join(str(raw).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def build_manifest_info_html(manifest, path: Path, max_chars: int) -> str:
    """Build simple HTML snippet with manifest info.

    Parameters
    ----------
    manifest
        Plugin manifest instance.
    path
        Filesystem path to the plugin directory.
    max_chars
        Maximum characters for description preview.
    """
    info_lines: list[str] = []

    # Name
    if hasattr(manifest, 'name') and manifest.name:
        if isinstance(manifest.name, dict):
            name = manifest.name.get('en', list(manifest.name.values())[0] if manifest.name else 'Unknown')
        else:
            name = str(manifest.name)
        info_lines.append(f"<b>Name:</b> {name}")

    # Authors
    if hasattr(manifest, 'authors') and manifest.authors:
        authors = ', '.join(manifest.authors) if isinstance(manifest.authors, list) else str(manifest.authors)
        info_lines.append(f"<b>Authors:</b> {authors}")

    # Description
    desc = description_preview(manifest, max_chars=max_chars)
    if desc:
        info_lines.append(f"<b>Description:</b> {html.escape(desc)}")

    # API versions
    if hasattr(manifest, 'api') and manifest.api:
        api_versions = ', '.join(manifest.api) if isinstance(manifest.api, list) else str(manifest.api)
        info_lines.append(f"<b>API Versions:</b> {api_versions}")

    # License
    if hasattr(manifest, 'license') and manifest.license:
        info_lines.append(f"<b>License:</b> {manifest.license}")

    # Directory
    info_lines.append(f"<b>Directory:</b> {path}")

    return '<br>'.join(info_lines)


def build_multiple_manifest_summary_html(entries: list[tuple[str, Path, object]], invalid_errors: list[str]) -> str:
    """Build HTML summary for multiple discovered plugins.

    Parameters
    ----------
    entries
        List of tuples ``(name, path, manifest)`` for valid plugins.
    invalid_errors
        List of error messages for invalid candidates.
    """
    items: list[str] = []
    for name, plugin_path, manifest in entries:
        display_name = (
            manifest.name.get('en', next(iter(manifest.name.values())))
            if hasattr(manifest, 'name') and isinstance(manifest.name, dict) and manifest.name
            else str(getattr(manifest, 'name', name))
        )
        items.append(f"<li><b>{display_name}</b> <span style='color:#666'>({plugin_path.name})</span></li>")

    html_parts = [
        f"<b>Found {len(entries)} valid plugins:</b>",
        "<ul>" + "".join(items) + "</ul>",
    ]
    if invalid_errors:
        html_parts.append("<div style='color:#d32f2f'>Some entries were invalid and will be skipped.</div>")
    return "".join(html_parts)
