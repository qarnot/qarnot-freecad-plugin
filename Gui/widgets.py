import inspect
import os

from PySide import QtGui, QtCore


class LogDisplayer(QtGui.QWidget):
    # A widget that consists in a window which displays stdout and stderr
    # in two read-only text edit. It is used to display tasks logs
    def __init__(self, stdout, stderr) -> None:
        super().__init__()
        self.initGui(stdout, stderr)

    def initGui(self, stdout, stderr):
        self.setWindowTitle("Log report")

        self.textEditStdout = QtGui.QTextEdit()
        self.textEditStdout.setReadOnly(True)
        self.textEditStdout.setText(stdout)
        if not len(stdout):
            self.textEditStdout.setText("Task has no stdout")

        self.textEditStderr = QtGui.QTextEdit()
        self.textEditStderr.setReadOnly(True)
        self.textEditStderr.setText(stderr)
        if not len(stderr):
            self.textEditStderr.setText("Task has no stderr")

        self.groupBoxStdout = QtGui.QGroupBox("Standard output :")
        self.groupBoxStdoutLayout = QtGui.QHBoxLayout()
        self.groupBoxStdoutLayout.addWidget(self.textEditStdout)
        self.groupBoxStdout.setLayout(self.groupBoxStdoutLayout)

        self.groupBoxStderr = QtGui.QGroupBox("Standard error :")
        self.groupBoxStderrLayout = QtGui.QHBoxLayout()
        self.groupBoxStderrLayout.addWidget(self.textEditStderr)
        self.groupBoxStderr.setLayout(self.groupBoxStderrLayout)

        self.layout = QtGui.QHBoxLayout()
        self.layout.addWidget(self.groupBoxStdout)
        self.layout.addWidget(self.groupBoxStderr)
        self.setLayout(self.layout)

        self.show()

    def sizeHint(self):
        return QtCore.QSize(800, 400)


class HelpDisplayer(QtGui.QWidget):
    # A simple class that consists in a pop up window displaying a quick help
    def __init__(self) -> None:
        super().__init__()
        self.initGui()

    def initGui(self) -> None:
        self.setWindowTitle("Help")
        self.textBrowserHelp = HtmlDisplayer('Resources/txt/help_string.html',
                                             self)

        self.layout = QtGui.QHBoxLayout()
        self.layout.addWidget(self.textBrowserHelp)
        self.setLayout(self.layout)

        self.show()

    def sizeHint(self):
        return QtCore.QSize(600, 400)


class HtmlDisplayer(QtGui.QTextBrowser):
    # A widget that displays html and open external links
    def __init__(self, local_filename: str = "",
                 parent: QtGui.QWidget = None) -> None:
        super().__init__(parent)
        self.dirpath = os.path.dirname(
            os.path.abspath(inspect.getfile(inspect.currentframe())))
        if local_filename != "":
            self.setHtmlFile(local_filename)
        self.setOpenExternalLinks(True)

    def setHtmlFile(self, local_filename: str) -> None:
        html = ""
        with open(f'{self.dirpath}/{local_filename}') as f:
            html = f.read(10000)
        self.setHtml(html)


class HyperLinkLabel(QtGui.QLabel):
    # A label that sends to a link when clicked on it
    def __init__(self, url: str = '', parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.cursor = QtGui.QCursor(QtCore.Qt.PointingHandCursor)
        self.setCursor(self.cursor)

    @property
    def url(self):
        return self._url

    @url.setter
    def url(self, val):
        self._url = val
        self.setToolTip(self._url)

    def mousePressEvent(self, event):
        QtGui.QDesktopServices.openUrl(self._url)
        super().mousePressEvent(event)
