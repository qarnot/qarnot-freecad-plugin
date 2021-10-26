from femenums import FemState
import os
import inspect
import re

from PySide import QtGui, QtCore

import FreeCAD as App

from controller import QarnotController
from Gui.widgets import \
    HelpDisplayer, HyperLinkLabel, LogDisplayer
from Gui.utils import insert_analysis_item, insert_document_item, \
    insert_solver_item, waitingSlot, list_documents, list_analysis, \
    list_solver, get_femstate_icon, format_task_output
from Gui.eventhandler import DocumentObserver, GuiControllerEventDelegate


class QarnotCloudComputingGUI(QtGui.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.controller = QarnotController(GuiControllerEventDelegate())
        self.children_windows = []
        self._working_dir = None
        self.initGui()
        self.initEventHandling()
        self.loadToken()
        if len(self.controller.old_tasks) or len(self.controller.tasks):
            self.controller.event_delegate.start_callback()
        self.show()

    def initGui(self) -> None:
        dirpath = os.path.dirname(
            os.path.abspath(inspect.getfile(inspect.currentframe())))
        # Window
        self.setWindowTitle('Qarnot computing')
        self.setMinimumSize(300, 300)
        # Connection state label
        self.labelConnState = QtGui.QLabel(
            text="<font color='grey'>No token</font>")
        self.labelConnState.setFrameStyle(QtGui.QFrame.StyledPanel |
                                          QtGui.QFrame.Raised)
        self.labelConnState.setAlignment(QtCore.Qt.AlignCenter)
        # Token button
        self.buttonToken = QtGui.QPushButton()
        self.buttonToken.setText('set token')
        self._token = None
        # Help button
        self.buttonHelp = QtGui.QPushButton('Help')
        self.buttonHelp.setIcon(self.style().standardIcon(
            QtGui.QStyle.SP_TitleBarContextHelpButton))
        # Solver selection
        self.treeWidgetSolver = QtGui.QTreeWidget()
        self.treeWidgetSolver.setHeaderHidden(True)
        self.actualizeSolverSelect()
        # Group box for simulation parameter (name, directory)
        self.groupBoxSimulation = QtGui.QGroupBox('Simulation settings')
        # Directory line edit
        self.lineEditDirectory = QtGui.QLineEdit()
        self.lineEditDirectory.setPlaceholderText(
            'Set directory ou use default')
        # Directory button
        self.buttonDirectory = QtGui.QPushButton()
        self.buttonDirectory.setIcon(QtGui.QIcon.fromTheme('folder-open'))
        # Simulation name edit
        self.lineEditName = QtGui.QLineEdit()
        self.lineEditName.setPlaceholderText('Choose simulation\'s name')
        # Start button
        self.buttonStart = QtGui.QPushButton(text=' Start ')
        self.buttonStart.setIcon(self.style().standardIcon(
            QtGui.QStyle.SP_ArrowForward))
        # State Label
        self.labelState = QtGui.QLabel('Click start to launch a simulation')
        # Label for control panel
        self.labelConPanel = QtGui.QLabel('Current tasks')
        font = QtGui.QFont(self.labelConPanel.font())
        font.setBold(True)
        font.setPointSize(11)
        self.labelConPanel.setFont(font)
        self.labelConPanel.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        # Label for external link to Qarnot Console
        self.hyperLinkConsole = HyperLinkLabel(
            'https://console.qarnot.com/app/tasks')
        self.hyperLinkConsole.setPixmap(QtGui.QPixmap(
            f'{dirpath}/Gui/Resources/img/console_link_icon.gif')
                                        .scaled(16, 16))
        self.hyperLinkConsole.setAlignment(
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        # Control panel
        self.treeWidgetPanel = QtGui.QTreeWidget()
        self.treeWidgetPanel.setHeaderLabels(['Name',
                                              'Start date',
                                              'status',
                                              'document'])
        self.treeWidgetPanel.setColumnWidth(1, 70)
        self.treeWidgetPanel.setColumnWidth(2, 45)
        self.actualizePanel()
        # Discard/stop button
        self.buttonStop = QtGui.QPushButton(text='Discard')
        self.buttonStop.setIcon(self.style().standardIcon(
            QtGui.QStyle.SP_DialogDiscardButton))
        # Log button
        self.buttonLog = QtGui.QPushButton(text='Log')
        self.buttonLog.setIcon(QtGui.QIcon.fromTheme('text-x-generic'))
        # Load button
        self.buttonLoad = QtGui.QPushButton(text='Load')
        self.buttonLoad.setIcon(QtGui.QIcon.fromTheme('emblem-downloads'))
        # Load all button
        self.buttonLoadAll = QtGui.QPushButton(text='Load all')
        self.buttonLoadAll.setIcon(QtGui.QIcon.fromTheme('emblem-downloads'))
        # Layout
        self.layout = QtGui.QVBoxLayout()
        hBoxToken = QtGui.QHBoxLayout()
        hBoxToken.addWidget(self.buttonToken)
        hBoxToken.addWidget(self.labelConnState)
        hBoxToken.addWidget(self.buttonHelp)
        self.layout.addLayout(hBoxToken)
        self.layout.addWidget(self.treeWidgetSolver)
        gridStart = QtGui.QGridLayout()
        gridStart.addWidget(self.lineEditDirectory, 1, 1)
        gridStart.addWidget(self.buttonDirectory, 1, 2)
        gridStart.addWidget(self.lineEditName, 2, 1)
        gridStart.addWidget(self.buttonStart, 2, 2)
        gridStart.addWidget(self.labelState, 3, 1, 1, 2)
        self.groupBoxSimulation.setLayout(gridStart)
        self.layout.addWidget(self.groupBoxSimulation)
        hBoxConsole = QtGui.QHBoxLayout()
        hBoxConsole.addStretch(1)
        hBoxConsoleLabel = QtGui.QHBoxLayout()
        hBoxConsoleLabel.addWidget(self.labelConPanel)
        hBoxConsoleLabel.addWidget(self.hyperLinkConsole)
        hBoxConsole.addLayout(hBoxConsoleLabel, 1)
        hBoxConsole.addStretch(1)
        self.layout.addSpacing(10)
        self.layout.addLayout(hBoxConsole)
        self.layout.addWidget(self.treeWidgetPanel)
        hboxButton = QtGui.QHBoxLayout()
        hboxButton.addWidget(self.buttonStop)
        hboxButton.addWidget(self.buttonLog)
        hboxButton.addWidget(self.buttonLoad)
        hboxButton.addWidget(self.buttonLoadAll)
        self.layout.addLayout(hboxButton)
        self.setLayout(self.layout)

    def initEventHandling(self) -> None:
        # Add a document observer to actualize the solver select panel
        # when some document change and new solver are created.
        # the scheduler has some delay to allow the object to be effectively
        # created before panel is actualized
        self.obs = DocumentObserver()
        self.solverScheduler = QtCore.QTimer()
        self.solverScheduler.timeout.connect(self.actualizeSolverSelect)
        self.solverScheduler.setInterval(200)
        self.solverScheduler.setSingleShot(True)
        App.addDocumentObserver(self.obs)

        self.buttonToken.clicked.connect(self.tokenDialog)
        self.buttonHelp.clicked.connect(self.displayHelp)
        self.buttonDirectory.clicked.connect(self.directoryDialog)
        self.buttonStart.clicked.connect(self.startNewSimulation)
        self.buttonLoad.clicked.connect(self.loadResult)
        self.buttonLoadAll.clicked.connect(self.loadAllResult)
        self.buttonStop.clicked.connect(self.stopAndDiscard)
        self.buttonLog.clicked.connect(self.displayLog)
        self.controller.event_delegate.state_changed.connect(
            self.actualizePanel)
        self.obs.document_changed.connect(self.scheduleActualizeSolver)

    #
    # Widgets' slots and event endling
    #
    @QtCore.Slot()
    def tokenDialog(self) -> None:
        # Display dialog box to set Qarnot token and establish connection
        text, ok = QtGui.QInputDialog.getText(
            self, 'Token', 'Enter your token',
            echo=QtGui.QLineEdit.Normal, text=self.token)
        if ok:
            self.token = str(text)

    @QtCore.Slot()
    def displayHelp(self) -> None:
        self.children_windows.append(HelpDisplayer())

    @QtCore.Slot()
    def directoryDialog(self) -> None:
        # Display a dialog box to chose one's working directory
        start_dir = None
        if self.working_dir is not None:
            start_dir = self.working_dir
        self.working_dir = QtGui.QFileDialog.getExistingDirectory(
            self, 'Chose a directory', start_dir)

    @waitingSlot
    def startNewSimulation(self) -> None:
        # Callback to start button. Starts current selected analysis
        solver = self.getSelectedSolver()
        if solver is None:
            App.Console.PrintError('Select a solver first\n')
            return
        if self.controller.conn is None:
            App.Console.PrintError(
                'Connection with Qarnot has not been ' +
                'established yet. Please fill in your token first\n')
            return
        self.labelState.setText('Writing files...')
        self.labelState.repaint()
        name = self.lineEditName.text()
        self.controller.start_fem(solver, name, self.working_dir)
        self.lineEditName.clear()
        self.labelState.setText('Task submitted')
        self.actualizePanel()

    @waitingSlot
    def loadResult(self) -> None:
        uuid = self.getSelectedTask()
        if uuid == '':
            return
        if (self.isOldTask(uuid) or self.controller.tasks[uuid].document_name
                not in App.listDocuments()):
            App.Console.PrintWarning('Cannot load this task. Check that the ' +
                                     'document is opened')
            return
        if self.controller.tasks[uuid].state == FemState.COMPUTING:
            App.Console.PrintWarning('Task is still in progress !')
            return
        elif self.controller.tasks[uuid].state == FemState.LOADED:
            return
        self.controller.load_result(uuid)
        self.actualizePanel()

    @waitingSlot
    def loadAllResult(self) -> None:
        self.controller.load_all()
        self.actualizePanel()

    @QtCore.Slot()
    def stopAndDiscard(self) -> None:
        # Stops and discards selected task
        uuid = self.getSelectedTask()
        if uuid != '':
            self.controller.delete_task(uuid)
            self.actualizePanel()

    @QtCore.Slot()
    def displayLog(self) -> None:
        uuid = self.getSelectedTask()
        if uuid != '':
            if not self.isOldTask(uuid):
                q_task = self.controller.tasks[uuid].task
            else:
                q_task = self.controller.old_tasks[uuid].task
            ld = LogDisplayer(format_task_output(q_task.stdout()),
                              format_task_output(q_task.stderr()))
            self.children_windows.append(ld)

    @QtCore.Slot()
    def actualizePanel(self) -> None:
        # Actualize tasks states
        self.treeWidgetPanel.clear()
        for task in self.controller.list_task():
            item = QtGui.QTreeWidgetItem()
            # uuid is stored in hidden data Qt.UserRole
            item.setData(0, QtCore.Qt.UserRole, task.uuid)
            item.setText(0, task.name)
            item.setText(1, task.creation_date.strftime('%H:%M:%S'))
            item.setIcon(2, get_femstate_icon(task.state))
            item.setText(3, task.document_name)
            self.treeWidgetPanel.addTopLevelItem(item)
        self.treeWidgetSolver.sortByColumn(1, QtCore.Qt.AscendingOrder)
        for task in self.controller.old_tasks.values():
            item = QtGui.QTreeWidgetItem()
            item.setData(0, QtCore.Qt.UserRole, task.uuid)
            item.setText(0, task.name)
            item.setText(1, task.creation_date.strftime('%H:%M:%S'))
            item.setText(3, task.document_path)
            for i in range(0, 4):
                item.setForeground(i, QtCore.Qt.gray)
            self.treeWidgetPanel.addTopLevelItem(item)

    @QtCore.Slot()
    def scheduleActualizeSolver(self) -> None:
        # Schedules a solver select actualization. The function is
        # not called directly to allow enough delay for objects to
        # be effectively created, since DocumentObserver functions
        # are called before action is taken
        if not self.solverScheduler.isActive():
            self.solverScheduler.start()

    @QtCore.Slot()
    def actualizeSolverSelect(self) -> None:
        # Actualize Solver selector
        self.controller.retrieve_all()
        current = self.getSelectedSolver()
        self.treeWidgetSolver.clear()
        docs = list_documents()
        for doc in docs:
            doc_item = insert_document_item(self.treeWidgetSolver, doc)
            anas = list_analysis(doc)
            for ana in anas:
                ana_item = insert_analysis_item(doc_item, ana)
                for solver in list_solver(ana):
                    item = insert_solver_item(ana_item, solver)
                    if current is not None and solver.Name == current.Name:
                        item.setSelected(True)

    def closeEvent(self, event):
        self.saveToken()
        App.removeDocumentObserver(self.obs)
        self.controller.event_delegate.stop_callback()
        QtGui.QApplication.restoreOverrideCursor()
        print("closed\n")
        super().closeEvent(event)

    #
    # Internal use functions
    #
    def getDocument(self):
        # Return current selected document
        selected = self.treeWidgetSolver.selectedItems()
        if len(selected) < 1:
            return None
        doc_item = selected[0].parent().parent()
        name = doc_item.data(0, QtCore.Qt.UserRole)
        if name in App.listDocuments().keys():
            return App.getDocument(doc_item.data(0, QtCore.Qt.UserRole))
        return None

    def getAnalysis(self):
        # Return selected analysis
        selected = self.treeWidgetSolver.selectedItems()
        if len(selected) < 1:
            return None
        name = selected[0].data(0, QtCore.Qt.UserRole)
        doc = self.getDocument()
        if doc is not None:
            return doc.getObject(name).getParentGroup()
        return None

    def getSelectedSolver(self):
        # Return selected Solver
        selected = self.treeWidgetSolver.selectedItems()
        if len(selected) < 1:
            return None
        name = selected[0].data(0, QtCore.Qt.UserRole)
        doc = self.getDocument()
        if doc is not None:
            return doc.getObject(name)
        return None

    def getSelectedTask(self) -> str:
        # Returns selected task uuid or '' if no task is selected
        selected = self.treeWidgetPanel.selectedItems()
        if len(selected) < 1:
            return ''
        return selected[0].data(0, QtCore.Qt.UserRole)

    def loadToken(self) -> None:
        # Try to load previously entered token and try
        # to establish connection. Return if succeeded
        if not os.path.isfile(self.tokenFile):
            return
        with open(self.tokenFile, 'r') as f:
            token = f.readline(1000)
            if re.fullmatch('[a-f0-9]{64}', token):
                self.token = token

    def saveToken(self) -> None:
        if self.token is None:
            return
        with open(self.tokenFile, 'w') as f:
            f.write(self.token)

    def isOldTask(self, uuid: str) -> bool:
        return uuid in self.controller.old_tasks

    #
    # Properties
    #
    @property
    def token(self) -> str:
        return self._token

    @token.setter
    def token(self, val):
        # set token value and try to establish a connection.
        # Then actualizes connection states desplayed by GUI
        self._token = val
        if self.controller.establish_connection(self._token):
            self.controller.retrieve_all()
            self.actualizePanel()
            self.labelConnState.setText(
                "<font color='green'>Connection established</font>")
        else:
            self.labelConnState.setText(
                "<font color='red'>Connection failed</font>")

    @property
    def tokenFile(self) -> str:
        return App.ConfigGet('UserAppData')+'qarnot.txt'

    @property
    def working_dir(self) -> str:
        if self._working_dir == '':
            self._working_dir = None
        return self._working_dir

    @working_dir.setter
    def working_dir(self, val: str):
        self._working_dir = val
        self.lineEditDirectory.setText(self._working_dir)
