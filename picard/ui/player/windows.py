# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2026 Philipp Wolfer
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
# along with this program; if not, see <https://www.gnu.org/licenses/>.

from datetime import timedelta
from functools import partial

from picard import log
from picard.file import File
from picard.util.thread import to_main

from .player import Player
from winrt.windows.foundation import Uri  # type: ignore[unresolved-import]
from winrt.windows.media import (  # type: ignore[unresolved-import]
    MediaPlaybackStatus,
    MediaPlaybackType,
    SystemMediaTransportControls,
    SystemMediaTransportControlsButton,
    SystemMediaTransportControlsTimelineProperties,
)
from winrt.windows.media.core import MediaSource  # type: ignore[unresolved-import]
from winrt.windows.media.playback import MediaPlayer  # type: ignore[unresolved-import]


class WindowsNowPlayingService:
    """
    Windows implementation of NowPlayingService using
    System Media Transport Controls (SMTC).
    """

    def __init__(self, player: Player):
        self._player = player
        self._smtc: SystemMediaTransportControls | None = None
        self._smtc_btn_handler = None
        self._enabled = False

    def enable(self):
        if self._enabled:
            return

        try:
            self._media_player = MediaPlayer()
            self._smtc = self._media_player.system_media_transport_controls

            # Activate playback context, otherwise Windows won't consider our
            # app active.
            # This feels wrong. It is wrong. It is also required.
            silent_uri = Uri("about:blank")
            self._media_player.source = MediaSource.create_from_uri(silent_uri)
            self._media_player.play()
        except Exception:
            log.exception("Failed to initialize SystemMediaTransportControls")
            return

        smtc = self._smtc
        smtc.is_enabled = True

        # Update current state
        self._on_playback_state_changed(self._player.playback_state)
        self._on_media_changed(self._player.current_file)
        smtc.playback_rate = self._player.playback_rate

        # Connect player signals
        self._player.playback_state_changed.connect(self._on_playback_state_changed)
        self._player.seeked.connect(self._on_seeked)
        self._player.duration_changed.connect(self._on_duration_changed)
        self._player.playback_rate_changed.connect(self._on_playback_rate_changed)
        self._player.media_changed.connect(self._on_media_changed)

        # Connect to playback buttons
        self._smtc_btn_handler = smtc.add_button_pressed(self._on_smtc_button_pressed)

        self._enabled = True
        log.debug("Windows Now Playing (SMTC) enabled")

    def disable(self):
        if not self._enabled:
            return

        # Stop fake playback
        self._media_player.close()

        # Disconnect signals
        self._player.playback_state_changed.disconnect(self._on_playback_state_changed)
        self._player.seeked.disconnect(self._on_seeked)
        self._player.duration_changed.disconnect(self._on_duration_changed)
        self._player.playback_rate_changed.disconnect(self._on_playback_rate_changed)
        self._player.media_changed.disconnect(self._on_media_changed)

        if self._smtc:
            if self._smtc_btn_handler:
                self._smtc.remove_button_pressed(self._smtc_btn_handler)
            self._smtc.is_enabled = False
            self._smtc = None

        self._enabled = False
        log.debug("Windows Now Playing (SMTC) disabled")

    def _on_smtc_button_pressed(self, sender, args):
        button = args.button

        log.debug("SMTC button pressed: %s", button)

        # SMTC events arrive on a SMTC thread. We need to pass them to the
        # player on the main thread to avoid threading issues in Qt.
        if button == SystemMediaTransportControlsButton.PLAY:
            to_main(self._player.play)
        elif button == SystemMediaTransportControlsButton.PAUSE:
            to_main(self._player.pause, True)
        elif button == SystemMediaTransportControlsButton.STOP:
            to_main(self._player.stop)
        elif button == SystemMediaTransportControlsButton.NEXT:
            to_main(self._player.play_next)
        elif button == SystemMediaTransportControlsButton.PREVIOUS:
            # Previous track is not supported, but we can jump to the start of the track
            to_main(partial(setattr, self._player, 'position', 0))

    def _on_playback_state_changed(self, state: Player.PlaybackState):
        if not self._smtc:
            return

        smtc = self._smtc

        if state == Player.PlaybackState.PLAYING:
            # The button status must match the state. Otherwise Windows
            # will disable buttons by itself
            smtc.is_play_enabled = False
            smtc.is_pause_enabled = True
            smtc.is_stop_enabled = True
            smtc.is_next_enabled = True
            smtc.is_previous_enabled = True
            status = MediaPlaybackStatus.PLAYING
        elif state == Player.PlaybackState.PAUSED:
            smtc.is_play_enabled = True
            smtc.is_pause_enabled = False
            smtc.is_stop_enabled = True
            smtc.is_next_enabled = True
            smtc.is_previous_enabled = True
            status = MediaPlaybackStatus.PAUSED
        else:
            smtc.is_play_enabled = True
            smtc.is_pause_enabled = False
            smtc.is_stop_enabled = False
            smtc.is_next_enabled = False
            smtc.is_previous_enabled = False
            status = MediaPlaybackStatus.STOPPED

        smtc.playback_status = status

    def _on_seeked(self, position: int):
        self._update_timeline_properties()

    def _on_duration_changed(self, duration: int):
        self._update_timeline_properties()

    def _on_playback_rate_changed(self, playback_rate: float):
        if not self._smtc:
            return

        self._smtc.playback_rate = playback_rate

    def _on_media_changed(self, file: File | None):
        if not self._smtc:
            return

        updater = self._smtc.display_updater
        updater.type = MediaPlaybackType.MUSIC

        if not file:
            updater.clear_all()
        else:
            music = updater.music_properties

            # Picard File provides these attributes
            m = file.metadata
            music.title = m['title']
            music.album_title = m['album']
            music.artist = m['artist']
            music.album_artist = m['albumartist']
            music.track_number = file.tracknumber
            music.genres.extend(m.getall('genre'))

        updater.update()
        self._update_timeline_properties()

    def _update_timeline_properties(self):
        if not self._smtc:
            return

        timeline = SystemMediaTransportControlsTimelineProperties()

        timeline.start_time = timedelta(0)
        timeline.min_seek_time = timedelta(0)
        timeline.position = timedelta(milliseconds=self._player.position)
        timeline.max_seek_time = timedelta(milliseconds=self._player.duration)
        timeline.end_time = timedelta(milliseconds=self._player.duration)

        self._smtc.update_timeline_properties(timeline)
