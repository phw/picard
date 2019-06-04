# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2004 Robert Kaye
# Copyright (C) 2006-2008, 2011 Lukáš Lalinský
# Copyright (C) 2008 Hendrik van Antwerpen
# Copyright (C) 2008 Will
# Copyright (C) 2010-2011, 2014, 2018-2019 Philipp Wolfer
# Copyright (C) 2011-2013 Michael Wiencek
# Copyright (C) 2012 Chad Wilson
# Copyright (C) 2012 Wieland Hoffmann
# Copyright (C) 2013-2015, 2018-2019 Laurent Monin
# Copyright (C) 2014, 2017 Sophist-UK
# Copyright (C) 2016 Rahul Raturi
# Copyright (C) 2016-2017 Sambhav Kothari
# Copyright (C) 2017 Antonio Larrosa
# Copyright (C) 2018 Vishal Choudhary
# Copyright (C) 2020 Ray Bouchard
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


from collections import defaultdict
import ntpath
import operator
import re

from PyQt5 import QtCore

from picard import config
from picard.const import QUERY_LIMIT
from picard.const.sys import IS_WIN
from picard.metadata import (
    Metadata,
    SimMatchRelease,
)
from picard.util import (
    album_artist_from_path,
    find_best_match,
    format_time,
)
from picard.util.imagelist import (
    add_metadata_images,
    remove_metadata_images,
    update_metadata_images,
)

from picard.ui.item import Item


class Cluster(QtCore.QObject, Item):

    # Weights for different elements when comparing a cluster to a release
    comparison_weights = {
        'album': 17,
        'albumartist': 6,
        'totaltracks': 5,
        'releasetype': 10,
        'releasecountry': 2,
        'format': 2,
        'date': 4,
    }

    def __init__(self, name, artist="", special=False, related_album=None, hide_if_empty=False):
        QtCore.QObject.__init__(self)
        self.item = None
        self.metadata = Metadata()
        self.metadata['album'] = name
        self.metadata['albumartist'] = artist
        self.metadata['totaltracks'] = 0
        self.special = special
        self.hide_if_empty = hide_if_empty
        self.related_album = related_album
        self.files = []
        self.lookup_task = None
        self.update_metadata_images_enabled = True

    def __repr__(self):
        if self.related_album:
            return '<Cluster %s %r>' % (
                self.related_album.id,
                self.related_album.metadata[u"album"] + '/' + self.metadata['album']
            )
        return '<Cluster %r>' % self.metadata['album']

    def __len__(self):
        return len(self.files)

    def _update_related_album(self, added_files=None, removed_files=None):
        if self.related_album:
            if added_files:
                add_metadata_images(self.related_album, added_files)
            if removed_files:
                remove_metadata_images(self.related_album, removed_files)
            self.related_album.update()

    def add_files(self, files):
        for file in files:
            self.metadata.length += file.metadata.length
            file._move(self)
            file.update(signal=False)
            if self.can_show_coverart:
                file.metadata_images_changed.connect(self.update_metadata_images)
        self.files.extend(files)
        self.metadata['totaltracks'] = len(self.files)
        self.item.add_files(files)
        if self.can_show_coverart:
            add_metadata_images(self, files)
        self._update_related_album(added_files=files)

    def add_file(self, file):
        self.add_files([file])

    def remove_file(self, file):
        self.metadata.length -= file.metadata.length
        self.files.remove(file)
        self.metadata['totaltracks'] = len(self.files)
        self.item.remove_file(file)
        if not self.special and self.get_num_files() == 0:
            self.tagger.remove_cluster(self)
        if self.can_show_coverart:
            file.metadata_images_changed.disconnect(self.update_metadata_images)
            remove_metadata_images(self, [file])
        self._update_related_album(removed_files=[file])

    def update(self):
        if self.item:
            self.item.update()

    def get_num_files(self):
        return len(self.files)

    def iterfiles(self, save=False):
        for file in self.files:
            yield file

    def can_save(self):
        """Return if this object can be saved."""
        if self.files:
            return True
        else:
            return False

    def can_remove(self):
        """Return if this object can be removed."""
        return not self.special

    def can_edit_tags(self):
        """Return if this object supports tag editing."""
        return True

    def can_analyze(self):
        """Return if this object can be fingerprinted."""
        return any([_file.can_analyze() for _file in self.files])

    def can_autotag(self):
        return True

    def can_refresh(self):
        return False

    def can_browser_lookup(self):
        return not self.special

    def can_view_info(self):
        if self.files:
            return True
        else:
            return False

    def is_album_like(self):
        return True

    def column(self, column):
        if column == 'title':
            return '%s (%d)' % (self.metadata['album'], len(self.files))
        elif (column == '~length' and self.special) or column == 'album':
            return ''
        elif column == '~length':
            return format_time(self.metadata.length)
        elif column == 'artist':
            return self.metadata['albumartist']
        elif column == 'tracknumber':
            return self.metadata['totaltracks']
        elif column == 'discnumber':
            return self.metadata['totaldiscs']
        return self.metadata[column]

    def _lookup_finished(self, document, http, error):
        self.lookup_task = None

        try:
            releases = document['releases']
        except (KeyError, TypeError):
            releases = None

        def statusbar(message):
            self.tagger.window.set_statusbar_message(
                message,
                {'album': self.metadata['album']},
                timeout=3000
            )

        if releases:
            albumid = self._match_to_album(releases, threshold=config.setting['cluster_lookup_threshold'])
        else:
            albumid = None

        if albumid is None:
            statusbar(N_("No matching releases for cluster %(album)s"))
        else:
            statusbar(N_("Cluster %(album)s identified!"))
            self.tagger.move_files_to_album(self.files, albumid)

    def _match_to_album(self, releases, threshold=0):
        # multiple matches -- calculate similarities to each of them
        def candidates():
            for release in releases:
                yield self.metadata.compare_to_release(release, Cluster.comparison_weights)

        no_match = SimMatchRelease(similarity=-1, release=None)
        best_match = find_best_match(candidates, no_match)

        if best_match.similarity < threshold:
            return None
        else:
            return best_match.result.release['id']

    def lookup_metadata(self):
        """Try to identify the cluster using the existing metadata."""
        if self.lookup_task:
            return
        self.tagger.window.set_statusbar_message(
            N_("Looking up the metadata for cluster %(album)s..."),
            {'album': self.metadata['album']}
        )
        self.lookup_task = self.tagger.mb_api.find_releases(self._lookup_finished,
            artist=self.metadata['albumartist'],
            release=self.metadata['album'],
            tracks=str(len(self.files)),
            limit=QUERY_LIMIT)

    def clear_lookup_task(self):
        if self.lookup_task:
            self.tagger.webservice.remove_task(self.lookup_task)
            self.lookup_task = None

    @staticmethod
    def cluster(files):
        win_compat = config.setting["windows_compatibility"] or IS_WIN
        cluster_list = defaultdict(TempCluster)
        for file in files:
            artist = file.metadata["albumartist"] or file.metadata["artist"]
            album = file.metadata["album"]

            # Improve clustering from directory structure if no existing tags
            # Only used for grouping and to provide cluster title / artist - not added to file tags.
            if win_compat:
                filename = ntpath.splitdrive(file.filename)[1]
            else:
                filename = file.filename
            album, artist = album_artist_from_path(filename, album, artist)

            token = tokenize(album)
            if not token:
                continue
            cluster_list[token].add(artist, album, file)

        for token, cluster in cluster_list.items():
            if len(cluster.files) <= 1:
                continue
            yield cluster.title, cluster.artist, cluster.files

    def enable_update_metadata_images(self, enabled):
        self.update_metadata_images_enabled = enabled

    def update_metadata_images(self):
        if self.update_metadata_images_enabled and self.can_show_coverart:
            update_metadata_images(self)


class UnclusteredFiles(Cluster):

    """Special cluster for 'Unmatched Files' which have not been clustered."""

    def __init__(self):
        super().__init__(_("Unclustered Files"), special=True)

    def add_files(self, files):
        super().add_files(files)
        self.tagger.window.enable_cluster(self.get_num_files() > 0)

    def add_file(self, file):
        super().add_file(file)
        self.tagger.window.enable_cluster(self.get_num_files() > 0)

    def remove_file(self, file):
        super().remove_file(file)
        self.tagger.window.enable_cluster(self.get_num_files() > 0)

    def lookup_metadata(self):
        self.tagger.autotag(self.files)

    def can_edit_tags(self):
        return False

    def can_autotag(self):
        return len(self.files) > 0

    def can_view_info(self):
        return False

    def can_remove(self):
        return len(self.files) > 0

    @property
    def can_show_coverart(self):
        return False


class ClusterList(list, Item):

    """A list of clusters."""

    def __init__(self):
        super().__init__()

    def __hash__(self):
        return id(self)

    def iterfiles(self, save=False):
        for cluster in self:
            for file in cluster.iterfiles(save):
                yield file

    def can_save(self):
        return len(self) > 0

    def can_analyze(self):
        return any([cluster.can_analyze() for cluster in self])

    def can_autotag(self):
        return len(self) > 0

    def can_browser_lookup(self):
        return False

    def lookup_metadata(self):
        for cluster in self:
            cluster.lookup_metadata()


class TempCluster:
    def __init__(self):
        self.files = []
        self.artists = defaultdict(lambda: 0)
        self.titles = defaultdict(lambda: 0)

    def add(self, artist, album, file):
        self.files.append(file)
        self.artists[artist] += 1
        self.titles[album] += 1

    @property
    def artist(self):
        return max(self.artists.items(), key=operator.itemgetter(1))[0]

    @property
    def title(self):
        return max(self.titles.items(), key=operator.itemgetter(1))[0]


_re_non_alphanum = re.compile(r'\W', re.UNICODE)
_re_spaces = re.compile(r'\s', re.UNICODE)
def tokenize(word):  # noqa: E302
    word = word.lower()
    token = _re_non_alphanum.sub('', word)
    return token if token else _re_spaces.sub('', word)
