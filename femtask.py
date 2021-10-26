from datetime import datetime
from dateutil import tz
from typing import List
from re import sub

import qarnot
from qarnot.exceptions import \
    MaxTaskException, NotEnoughCreditsException, UnauthorizedException
from qarnot.task import Task
from qarnot.bucket import Bucket
from femenums import SolverType, FemState

import FreeCAD as App
from femsolver import run, report
from femtools.ccxtools import CcxTools
import femsolver.calculix.tasks as ccxt


def make_unique_name(name_list: List[str], name: str) -> str:
    # Appends a number to name to make it unique,
    # e.g different from any name in name_list
    if name not in name_list:
        return name
    i = 1
    while f'{name}{i}' in name_list:
        i = i + 1
    return f'{name}{i}'


def rectify_bucket_name(name_list: List[str], name: str) -> str:
    # Modify a name so it matches the bucket regex and is unique
    # Does so by replacing not allowed character by _
    name = sub("[^a-zA-Z0-9]", "_", name)
    if len(name) > 250:
        name = name[0:250]
    return make_unique_name(name_list, name)


class QarnotFemTask():
    # A class to represent a fem task to compute on qarnot

    def __init__(self, solver, name: str, working_dir: str = None) -> None:
        # Create the fem task and set up the target directory.
        super().__init__()

        # Tasks and bucket from qarnot sdk
        self.task: Task = None
        self.input_bucket: Bucket = None
        self.output_bucket: Bucket = None

        self.solver = solver
        self.solver_type: SolverType = SolverType.UNKNOWN
        self.name: str = name
        self.machine = None
        self.ccx = None
        self.working_dir = working_dir
        self.file = None
        self.state: FemState = FemState.SETTING_UP

        self.result_object_names: List[str] = []

        self.findSolverType()
        if self.solver_type == SolverType.UNKNOWN:
            raise AttributeError("solver type not supported")
        self.setMachineAndDirectory()

    def delete(self):
        # Delete Qarnot task and buckets
        if self.task is not None:
            self.task.delete(purge_resources=True, purge_results=True)
            self.task = None
        if self.machine is not None:
            del self.machine
            self.machine = None

    def findSolverType(self):
        # Find solver type
        if self.solver.Proxy.Type == "Fem::SolverCcxTools":
            self.solver_type = SolverType.CCX_TOOLS
        elif self.solver.Proxy.Type == "Fem::SolverElmer":
            self.solver_type = SolverType.ELMER
        elif self.solver.Proxy.Type == "Fem::SolverCalculix":
            self.solver_type = SolverType.CCX
        elif self.solver.Proxy.Type == "Fem::SolverZ88":
            self.solver_type = SolverType.Z88
        # TODO : add other solvers
        else:
            self.solver_type == SolverType.UNKNOWN

    def setMachineAndDirectory(self):
        # Creates machine or tool (old ccxTools works differently from other
        # solvers) and define the working directory
        if self.solver_type != SolverType.CCX_TOOLS:
            self.machine = run._createMachine(self.solver, self.working_dir,
                                              testmode=False)
            self.machine._confTasks()
            self.working_dir = self.machine.directory
        else:
            self.ccx = CcxTools(self.solver)
            self.ccx.update_objects()
            self.ccx.setup_working_dir(self.working_dir)
            self.working_dir = self.ccx.working_dir

    def prepare(self) -> bool:
        # Executes the prepare operation of a fem task,
        # e.g writing the input files for the simulation
        # Returns wether it was a success
        self.state = FemState.WRITING
        if self.solver_type == SolverType.CCX_TOOLS:
            message = self.ccx.check_prerequisites()
            if not message:
                self.ccx.write_inp_file()
                self.file = self.ccx.inp_file_name.split('/')[-1].split('.')[0]
            else:
                App.Console.PrintError(message)
                return False

        else:
            self.machine.reset()
            self.machine.target = run.PREPARE
            self.machine.start()
            self.machine.join()
            if self.machine.failed is True:
                report.displayLog(self.machine.report)
                return False
            if self.solver_type == SolverType.CCX:
                self.file = ccxt._inputFileName
        return True

    def create_bucket(self, conn: qarnot.Connection) -> None:
        # Create input and output bucket to manage file
        # input and output toward Qarnot servers
        # Should be internal use
        bucket_names = [buck.description for buck in conn.buckets()]

        in_name = rectify_bucket_name(bucket_names,
                                      f'input-resource-{self.name}')
        self.input_bucket = conn.create_bucket(in_name)
        self.input_bucket.add_directory(self.working_dir)
        self.task.resources.append(self.input_bucket)

        out_name = rectify_bucket_name(bucket_names, f'output-{self.name}')
        self.output_bucket = conn.create_bucket(out_name)
        self.task.results = self.output_bucket

    def create_task(self, conn: qarnot.Connection) -> None:
        # Create task and set docker repository and command
        # Should be internal use
        self.task = conn.create_task(self.name, 'docker-batch', 1)
        self.task.tags.append('FreeCAD macro')
        self.task.constants['FREECAD_WORKING_DIR'] = self.working_dir
        self.task.constants['FREECAD_DOCUMENT'] = self.solver.Document.FileName
        self.task.constants['FREECAD_SOLVER'] = self.solver.Name
        if (self.solver_type == SolverType.CCX_TOOLS or
                self.solver_type == SolverType.CCX):
            if self.solver_type == SolverType.CCX_TOOLS:
                self.task.constants['CCX_TOOLS_INP_FILENAME'] = \
                    self.ccx.inp_file_name
            self.task.constants['DOCKER_REPO'] = 'calculix/ccx'
            self.task.constants['DOCKER_CMD'] = f'bash -c \
                "export OMP_NUM_THREADS=$(nproc) && ccx -i {self.file}" '
        elif self.solver_type == SolverType.ELMER:
            self.task.constants['DOCKER_REPO'] = 'nwrichmond/elmerice'
            self.task.constants['DOCKER_CMD'] = 'bash -c \
                "/usr/local/Elmer-devel/bin/ElmerSolver" '
        elif self.solver_type == SolverType.Z88:
            self.task.constants['DOCKER_REPO'] = 'adlf/z88os'
            self.task.constants['DOCKER_CMD'] = 'bash -c \
                "z88r -t -choly && z88r -c -choly" '

    def run(self, conn: qarnot.Connection) -> None:
        # Create the task and submits it
        if not self.prepare():
            # Writing failed.
            return
        self.create_task(conn)
        try:
            self.create_bucket(conn)
        except IOError as err:
            App.Console.PrintError("Unable to create bucket. " + err.strerror)
            return
        except Exception as err:
            App.Console.PrintError(err)
            return
        try:
            self.task.submit()
        except MaxTaskException:
            App.Console.PrintError("You have reached the maximum \
                number of task you can simultaneously have on Qarnot. \
                You may go to https://console.qarnot.com/app/tasks \
                to clean up old, not-deleted tasks or consider upgrading \
                your account\n")
        except NotEnoughCreditsException:
            App.Console.PrintError("You don't have anymore credits to perform \
                this task. Please recharge on \
                https://account.qarnot.com/account\n")
        except UnauthorizedException as err:
            App.Console.PrintError(err)
        except Exception as err:
            App.console.PrintError("Unable to start task. An error happened\n")
            App.console.PrintError(err)
        self.state = FemState.COMPUTING

    def wait_callback(self) -> bool:
        # Test if task is done then retrieve result or report errors.
        # Return wether the task is done
        if self.state > FemState.COMPUTING:
            return True
        done = self.task.wait(0.001)
        if not done:
            return False
        if self.task.state == 'Failure':
            App.Console.PrintError(f'Error on task {self.name}\n : \
                {self.task.errors[0]}. See log for more details')
            self.state = FemState.ERROR
        else:
            self.task.download_results(output_dir=self.working_dir)
            self.state = FemState.FINISHED
        return True

    def load_result(self) -> List[str]:
        # Load fem results into FreeCAD. Newly created objects are renamed
        # afterwards to avoid confusion when several simulations are loaded
        if (self.state == FemState.COMPUTING or
                self.state == FemState.SETTING_UP):
            raise RuntimeError("attempted to load an unfinished task")
        objects_before = self.solver.Document.findObjects()

        if self.solver_type == SolverType.CCX_TOOLS:
            self.ccx.load_results()
        elif self.solver_type == SolverType.ELMER:
            # Elmer auto overrites results if ElmerResult already exists
            try:
                self.solver.ElmerResult = None
            except AttributeError:
                # Discard exception is solver has no ElmerResult yet
                pass
            self.machine.results.run()
        else:
            self.machine.results.run()

        objects_after = self.solver.Document.findObjects()
        for obj in objects_after:
            if obj not in objects_before:
                obj.Label = f'{self.name}_{obj.Label}'
                self.result_object_names.append(obj.Name)
        self.state = FemState.LOADED

    @property
    def uuid(self) -> str:
        if self.task is None:
            return ""
        return self.task.uuid

    @property
    def creation_date(self) -> datetime:
        return self.task.creation_date.replace(
            tzinfo=tz.tzutc()).astimezone(tz=None)

    @property
    def document_name(self) -> str:
        return self.solver.Document.Name


class QarnotOldFemTask():
    # A class to represent a task that was previously sent on
    # qarnot and that may be retrieved

    def __init__(self, task: Task) -> None:
        self.task: Task = task
        self.complete: bool = False
        self.missing_constants: List[str] = []
        for const in ['FREECAD_DOCUMENT',
                      'FREECAD_SOLVER',
                      'FREECAD_WORKING_DIR']:
            if const not in task.constants.keys():
                self.missing_constants.append(const)
        if ('FREECAD_SOLVER' not in self.missing_constants and
                'CcxTools' in self.solver_name and
                'CCX_TOOLS_INP_FILENAME' not in task.constants.keys()):
            self.missing_constants.append('CCX_TOOLS_INP_FILENAME')
        if len(self.missing_constants) == 0:
            self.complete = True

    def delete(self) -> None:
        self.task.delete(purge_resources=True, purge_results=True)
        self.task = None

    @property
    def uuid(self) -> str:
        return self.task.uuid

    @property
    def name(self) -> str:
        return self.task.name

    @property
    def creation_date(self) -> str:
        return self.task.creation_date.replace(
            tzinfo=tz.tzutc()).astimezone(tz=None)

    @property
    def document_path(self) -> str:
        return self.task.constants['FREECAD_DOCUMENT']

    @property
    def solver_name(self) -> str:
        return self.task.constants['FREECAD_SOLVER']

    @property
    def working_dir(self) -> str:
        return self.task.constants['FREECAD_WORKING_DIR']

    @property
    def ccx_inp_filename(self) -> str:
        return self.task.constants['CCX_TOOLS_INP_FILENAME']

    @staticmethod
    def is_complete(task: Task):
        t = QarnotOldFemTask(task)
        return t.complete
