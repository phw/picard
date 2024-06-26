# Form implementation generated from reading ui file 'ui/infodialog.ui'
#
# Created by: PyQt6 UI code generator 6.6.1
#
# Automatically generated - do not edit.
# Use `python setup.py build_ui` to update it.

from PyQt6 import (
    QtCore,
    QtGui,
    QtWidgets,
)

from picard.i18n import gettext as _


class Ui_InfoDialog(object):
    def setupUi(self, InfoDialog):
        InfoDialog.setObjectName("InfoDialog")
        InfoDialog.resize(665, 436)
        self.verticalLayout = QtWidgets.QVBoxLayout(InfoDialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.tabWidget = QtWidgets.QTabWidget(parent=InfoDialog)
        self.tabWidget.setObjectName("tabWidget")
        self.info_tab = QtWidgets.QWidget()
        self.info_tab.setObjectName("info_tab")
        self.vboxlayout = QtWidgets.QVBoxLayout(self.info_tab)
        self.vboxlayout.setObjectName("vboxlayout")
        self.info_scroll = QtWidgets.QScrollArea(parent=self.info_tab)
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setObjectName("info_scroll")
        self.scrollAreaWidgetContents = QtWidgets.QWidget()
        self.scrollAreaWidgetContents.setEnabled(True)
        self.scrollAreaWidgetContents.setGeometry(QtCore.QRect(0, 0, 623, 361))
        self.scrollAreaWidgetContents.setObjectName("scrollAreaWidgetContents")
        self.verticalLayoutLabel = QtWidgets.QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayoutLabel.setObjectName("verticalLayoutLabel")
        self.info = QtWidgets.QLabel(parent=self.scrollAreaWidgetContents)
        self.info.setText("")
        self.info.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeading|QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignTop)
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse|QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard|QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info.setObjectName("info")
        self.verticalLayoutLabel.addWidget(self.info)
        self.info_scroll.setWidget(self.scrollAreaWidgetContents)
        self.vboxlayout.addWidget(self.info_scroll)
        self.tabWidget.addTab(self.info_tab, "")
        self.error_tab = QtWidgets.QWidget()
        self.error_tab.setObjectName("error_tab")
        self.vboxlayout1 = QtWidgets.QVBoxLayout(self.error_tab)
        self.vboxlayout1.setObjectName("vboxlayout1")
        self.scrollArea = QtWidgets.QScrollArea(parent=self.error_tab)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setObjectName("scrollArea")
        self.scrollAreaWidgetContents_3 = QtWidgets.QWidget()
        self.scrollAreaWidgetContents_3.setGeometry(QtCore.QRect(0, 0, 623, 361))
        self.scrollAreaWidgetContents_3.setObjectName("scrollAreaWidgetContents_3")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.scrollAreaWidgetContents_3)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.error = QtWidgets.QLabel(parent=self.scrollAreaWidgetContents_3)
        self.error.setText("")
        self.error.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeading|QtCore.Qt.AlignmentFlag.AlignLeft|QtCore.Qt.AlignmentFlag.AlignTop)
        self.error.setWordWrap(True)
        self.error.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse|QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard|QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error.setObjectName("error")
        self.verticalLayout_2.addWidget(self.error)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents_3)
        self.vboxlayout1.addWidget(self.scrollArea)
        self.tabWidget.addTab(self.error_tab, "")
        self.artwork_tab = QtWidgets.QWidget()
        self.artwork_tab.setObjectName("artwork_tab")
        self.vboxlayout2 = QtWidgets.QVBoxLayout(self.artwork_tab)
        self.vboxlayout2.setObjectName("vboxlayout2")
        self.tabWidget.addTab(self.artwork_tab, "")
        self.verticalLayout.addWidget(self.tabWidget)
        self.buttonBox = QtWidgets.QDialogButtonBox(parent=InfoDialog)
        self.buttonBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.NoButton)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(InfoDialog)
        self.tabWidget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(InfoDialog)
        InfoDialog.setTabOrder(self.tabWidget, self.buttonBox)

    def retranslateUi(self, InfoDialog):
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.info_tab), _("&Info"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.error_tab), _("&Error"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.artwork_tab), _("A&rtwork"))
