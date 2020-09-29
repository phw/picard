# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2020 Philipp Wolfer
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

from PyQt5.QtCore import (
    Q_CLASSINFO,
    QCoreApplication,
    QObject,
    QUrl,
    pyqtSlot,
)
from PyQt5.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusMessage,
)

from picard import log


def uri_to_path(uri):
    return os.path.normpath(os.path.realpath(QUrl(uri).toLocalFile()))


class FreedesktopApplicationService(QObject):

    def __init__(self, bus):
        QObject.__init__(self)
        self._path = '/org/musicbrainz/Picard'
        self._dbus_adaptor = FreedesktopApplicationAdaptor(self)
        self._available = bus.registerObject(self._path, self)

    @property
    def tagger(self):
        return QCoreApplication.instance()

    def activate(self, platform_data=None):
        log.debug("FreedesktopApplicationService.activate(%r)" % platform_data)
        self.tagger.bring_tagger_front()

    def open(self, uris=None, platform_data=None):
        log.debug("FreedesktopApplicationService.open(%r, %r)" % (uris, platform_data))
        if uris:
            paths = [uri_to_path(uri) for uri in uris]
            self.tagger.add_paths(paths)
            self.tagger.bring_tagger_front()

    def activate_action(self, action_name="", parameter=None, platform_data=None):
        log.debug("FreedesktopApplicationService.activate_action(%r, %r, %r)" % (action_name, parameter, platform_data))
        pass


class FreedesktopApplicationAdaptor(QDBusAbstractAdaptor):
    """ This provides the DBus adaptor to the outside world"""

    # See https://specifications.freedesktop.org/desktop-entry-spec/latest/ar01s08.html
    DBUS_INTERFACE = 'org.freedesktop.Application'
    Q_CLASSINFO("D-Bus Interface", DBUS_INTERFACE)
    Q_CLASSINFO("D-Bus Introspection",
        '<interface name="%s">\n'
        '  <method name="Activate">\n'
        '    <arg type="a{sv}" name="platform-data" direction="in"/>\n'
        '  </method>\n'
        '  <method name="Open">\n'
        '    <arg type="as" name="uris" direction="in"/>\n'
        '    <arg type="a{sv}" name="platform-data" direction="in"/>\n'
        '  </method>\n'
        '  <method name="ActivateAction">\n'
        '    <arg type="s" name="action-name" direction="in"/>\n'
        '    <arg type="av" name="parameter" direction="in"/>\n'
        '    <arg type="a{sv}" name="platform-data" direction="in"/>\n'
        '  </method>\n'
        '</interface>' % DBUS_INTERFACE)

    @pyqtSlot(QDBusMessage)
    def Activate(self, message):
        args = message.arguments()
        self.parent().activate(*args)

    @pyqtSlot(QDBusMessage, name="Open")
    def open(self, message):
        args = message.arguments()
        self.parent().open(*args)

    @pyqtSlot(QDBusMessage, name="ActivateAction")
    def activate_action(self, message):
        args = message.arguments()
        self.parent().activate_action(*args)
