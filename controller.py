from typing import Dict, List, Optional
import qarnot
from qarnot.task import Task
from time import localtime, strftime

from PySide import QtCore

import FreeCAD as App

from femtask import QarnotFemTask, QarnotOldFemTask
from femenums import FemState, SolverType


class ControllerEventDelegate(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        self.controller: Optional[QarnotController] = None

    def on_connection_established(self):
        pass

    def on_connection_failed(self, err: Exception):
        pass

    def on_task_submitted(self, uuid: str):
        pass

    def on_task_retrieved(self, uuid: str):
        pass

    def on_task_loaded(self, uuid: str):
        pass

    def on_task_deleted(self, uuid: str):
        pass

    def on_task_finished(self, uuid: str):
        pass

    def on_task_failed(self, uuid: str):
        pass


class QarnotController(QtCore.QObject):
    # This class is used to oversee Femtasks management. It encapsulate
    # a Qarnot connection and keeps a list of sent Femtasks. It can also
    # retrieve previous tasks and keeps a list of these previous task
    # in self.old_tasks
    # The class also include an event delegate which can be used to handle
    # events in a gui or multi threaded environnement

    def __init__(self, event_delegate: ControllerEventDelegate
                 = ControllerEventDelegate()) -> None:
        super().__init__()
        self.conn: qarnot.Connection = None
        self.tasks: Dict[str, QarnotFemTask] = {}
        self.old_tasks: Dict[str, QarnotOldFemTask] = {}
        self.event_delegate = event_delegate
        self.event_delegate.controller = self

    def establish_connection(self, token: str) -> bool:
        # Establish a Qarnot connection with the given
        # token and return if it was successful.
        self.conn = None
        try:
            self.conn = qarnot.Connection(client_token=token)
            self.event_delegate.on_connection_established()
            for t in self.find_old_tasks():
                old_task = QarnotOldFemTask(t)
                if old_task.complete:
                    self.old_tasks[old_task.uuid] = old_task
        except Exception as err:
            self.event_delegate.on_connection_failed(err)
        return self.conn is not None

    def start_fem(self, solver, name: str = '',
                  working_dir: str = None) -> None:
        # Start a fem calculation. If no name is given,
        # an arbitrary name based on launch time will be given
        if name is None or name == '':
            name = f'{solver.Label}_{strftime("%H.%M.%S", localtime())}'
        if self.conn is None:
            raise RuntimeError('Connection with Qarnot ' +
                               'has not been established yet\n')
        t = None
        try:
            t = QarnotFemTask(solver, name, working_dir)
        except Exception as err:
            App.Console.PrintError(err)
            return
        try:
            t.run(self.conn)
            if t is not None and t.state == FemState.COMPUTING:
                self.tasks[t.uuid] = t
                self.event_delegate.on_task_submitted(t.uuid)
        except Exception as err:
            App.Console.PrintError(err)
            del t

    def load_result(self, uuid: str) -> None:
        # Load result from task
        self.tasks[uuid].load_result()
        self.event_delegate.on_task_loaded(uuid)

    def load_all(self) -> None:
        # Load results from all tasks in LOADING states
        task_to_load = self.list_task([FemState.FINISHED])
        for task in task_to_load:
            self.load_result(task.uuid)

    def delete_task(self, uuid: str) -> None:
        # Abort if needed and deletes task or old task
        if uuid in self.tasks:
            t = self.tasks[uuid]
        elif uuid in self.old_tasks:
            t = self.old_tasks[uuid]
        else:
            return
        try:
            t.task.abort()
        except qarnot.exceptions.QarnotGenericException:
            # Discard exception raised if task is not running
            pass
        except Exception as err:
            App.Console.PrintError(err)
        finally:
            t.delete()
            del t
            if uuid in self.tasks:
                self.tasks.pop(uuid)
            elif uuid in self.old_tasks:
                self.old_tasks.pop(uuid)
            self.event_delegate.on_task_deleted(uuid)

    def actualize_tasks(self) -> None:
        # Call tasks wait callbacks and check if states have changed
        for t in self.list_task():
            if t.state != FemState.COMPUTING:
                continue
            t.wait_callback()
            if t.state == FemState.FINISHED:
                self.event_delegate.on_task_finished(t.uuid)
            elif t.state == FemState.ERROR:
                self.event_delegate.on_task_failed(t.uuid)

    #
    # Infos and general methods
    #
    def is_computing(self) -> bool:
        # Returns if at least one task is currently computing
        for t in self.list_task():
            if t.state == FemState.COMPUTING:
                return True
        return False

    def list_task(self, states: Optional[List[FemState]] = None) \
            -> List[QarnotFemTask]:
        # Return the list of task that are in the given state,
        # or all if state is not specified
        if states is None:
            return list(self.tasks.values())
        return [task for task in self.tasks.values() if task.state in states]

    #
    # Retrieving and old task management
    #
    def find_old_tasks(self) -> List[Task]:
        # Return the list of tasks that were sent with the 'FreeCAD macro'
        # tag but are not in the current dictionnary, e.g task that were
        # presumably sent by previous occurrences of the macro
        old = []
        for task in self.conn.tasks(['FreeCAD macro']):
            if task.uuid not in self.tasks:
                old.append(task)
        return old

    @staticmethod
    def retrieve_solver(task: QarnotOldFemTask) -> App.DocumentObject:
        # Try to retrieve solver from tasks constants and returns
        # the solver or None
        if not task.complete:
            return None
        doc = None
        for d in App.listDocuments().values():
            if d.FileName == task.document_path:
                doc = d
        if doc is None:
            return None
        return doc.getObject(task.solver_name)

    @staticmethod
    def is_retrievable(task: QarnotOldFemTask) -> bool:
        # Tells if the task is retrievable which is the case if:
        #   - the task has the correct constants
        #   - the document used to send the task is open and has not moved
        #   - the solver used is still presents
        if not task.complete:
            return False
        solver = QarnotController.retrieve_solver(task)
        return solver is not None

    @staticmethod
    def create_fem_task_from_old(task: QarnotOldFemTask) -> QarnotFemTask:
        if not QarnotController.is_retrievable(task):
            raise RuntimeError("task is not complete")
        solver = QarnotController.retrieve_solver(task)
        t = QarnotFemTask(solver, task.name, task.working_dir)
        q_task = task.task
        t.task = q_task
        t.input_bucket = q_task.resources[0]
        t.output_bucket = q_task.results
        if t.solver_type == SolverType.CCX_TOOLS:
            t.ccx.inp_file_name = task.ccx_inp_filename
        return t

    def retrieve_task(self, task: QarnotOldFemTask):
        # retrieve the old task and add it to the current task dictionary
        t = QarnotController.create_fem_task_from_old(task)
        t.state = FemState.COMPUTING
        self.tasks[task.uuid] = t
        self.old_tasks.pop(task.uuid)
        t.wait_callback()
        self.event_delegate.on_task_retrieved(task.uuid)

    def retrieve_all(self):
        for key in list(self.old_tasks.keys()):
            task = self.old_tasks[key]
            if QarnotController.is_retrievable(task):
                self.retrieve_task(task)
