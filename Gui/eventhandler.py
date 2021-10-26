from femenums import FemState
from controller import ControllerEventDelegate

from PySide import QtCore

import FreeCAD as App


class DocumentObserver(QtCore.QObject):
    # A simple document observer class use to tell the window to
    # actualize when it's solver selector panel.
    document_changed = QtCore.Signal()

    def __init__(self):
        super().__init__()

    def slotActivateDocument(self, doc):
        self.document_changed.emit()

    def slotCreatedDocument(self, doc):
        self.document_changed.emit()

    def slotDeletedDocument(self, doc):
        self.document_changed.emit()

    def slotChangedObject(self, obj, prop):
        if (obj.TypeId == 'Fem::FemSolverObjectPython' or
                obj.TypeId == 'Fem::FemAnalysis') and prop == 'Label':
            self.document_changed.emit()

    def slotCreatedObject(self, obj):
        if (obj.TypeId == 'Fem::FemSolverObjectPython' or
                obj.TypeId == 'Fem::FemAnalysis'):
            self.document_changed.emit()

    def slotDeletedObject(self, obj):
        if (obj.TypeId == 'Fem::FemSolverObjectPython' or
                obj.TypeId == 'Fem::FemAnalysis'):
            self.document_changed.emit()


class GuiControllerEventDelegate(ControllerEventDelegate):
    # The event delegate used by the GUI
    state_changed = QtCore.Signal()
    task_finished = QtCore.Signal(str)
    task_submitted = QtCore.Signal(str)
    task_failed = QtCore.Signal(str)

    def __init__(self) -> None:
        super().__init__()
        # Timer is used to periodically call the callback function that
        # actualizes tasks' states. Timer_interval defines the time between
        # each callback calls. If, it is set to a non positive value, no
        # callback will be called.
        # The state_changed signal is made so that when in occurs multiple
        # in a row, only when signal is emitted, thanks to a timer that is
        # reset

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.actualize_tasks)
        self.timer_interval = 2000

        self.state_changed_timer = QtCore.QTimer(self)
        self.state_changed_timer.timeout.connect(self.state_changed.emit)
        self.state_changed_timer.setSingleShot(True)
        self.state_changed_timer.setInterval(50)

    def on_task_submitted(self, uuid: str) -> None:
        self.start_callback()
        self.task_submitted.emit(uuid)
        self.send_state_change()
        App.Console.PrintMessage(
            f'task {self.controller.tasks[uuid].name} submitted\n')

    def on_task_finished(self, uuid: str) -> None:
        self.task_finished.emit(uuid)
        self.send_state_change()

    def on_task_loaded(self, uuid: str):
        self.schedule_callback(self.timer_interval)
        self.controller.delete_task(uuid)
        self.send_state_change()

    def on_task_retrieved(self, uuid: str):
        self.start_callback()
        self.send_state_change()

    def on_task_deleted(self, uuid: str):
        self.send_state_change()

    def on_task_failed(self, uuid: str):
        self.send_state_change()

    def on_connection_established(self):
        App.Console.PrintMessage('Connection established with Qarnot !\n')

    def on_connection_failed(self, err: Exception):
        App.Console.PrintError('Unable to connect to Qarnot. ' +
                               'Check your token and internet connection\n')

    @QtCore.Slot()
    def actualize_tasks(self) -> None:
        # Call tasks wait callbacks and check if states have changed
        for t in self.controller.list_task():
            if t.state != FemState.COMPUTING:
                continue
            t.wait_callback()
            if t.state == FemState.FINISHED:
                self.on_task_finished(t.uuid)
            elif t.state == FemState.ERROR:
                self.on_task_failed(t.uuid)
            elif t.state != FemState.COMPUTING:
                self.send_state_change()
        if not self.controller.is_computing():
            self.stop_callback()

    def start_callback(self) -> None:
        # Starts the callback that will periodically actualize tasks' state
        if self.timer_interval > 0 and not self.timer.isActive():
            self.timer.start(self.timer_interval)

    def stop_callback(self) -> None:
        # Starts the callback that periodically actualize tasks' state
        self.timer.stop()

    def schedule_callback(self, time: int = 200) -> None:
        # Schedule a callback call after time ms if timer is not active
        if self.timer_interval > 0 and not self.timer.isActive():
            self.timer.singleShot(time, self.actualize_tasks)

    def send_state_change(self):
        self.state_changed_timer.start()
