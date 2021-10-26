import functools
from typing import List
from femenums import FemState

from PySide import QtGui, QtCore

import FreeCAD as App


def waitingSlot(func):
    # Decorates a slot (the @QtCore.Slot is included) so that the cursor
    # is changed to Qt.WaitCursor before and reset after the slot is finished
    @functools.wraps(func)
    @QtCore.Slot()
    def wrapper_waiting(*args, **kwargs):
        QtGui.QApplication.setOverrideCursor(
            QtGui.QCursor(QtCore.Qt.WaitCursor))
        value = func(*args, **kwargs)
        QtGui.QApplication.restoreOverrideCursor()
        return value
    return wrapper_waiting


def insert_document_item(
        tree_widget: QtGui.QTreeWidget,
        doc: App.Document) -> QtGui.QTreeWidgetItem:
    # Insert an item representing a document to the tree_widget and returns it
    item = QtGui.QTreeWidgetItem()
    item.setText(0, doc.Name)
    item.setIcon(0, QtGui.QIcon(':/icons/Document.svg'))
    item.setFlags(QtCore.Qt.ItemIsEnabled)
    # uniquely identifying name is stored in hidden data Qt.UserRole
    item.setData(0, QtCore.Qt.UserRole, doc.Name)
    tree_widget.addTopLevelItem(item)
    item.setExpanded(True)
    return item


def insert_analysis_item(
        doc_item: QtGui.QTreeWidgetItem,
        ana: App.DocumentObjectGroup) -> QtGui.QTreeWidgetItem:
    # Insert an item representing an analysis to the tree_widget and returns it
    item = QtGui.QTreeWidgetItem()
    item.setText(0, ana.Label)
    item.setIcon(0, ana.ViewObject.Icon)
    item.setFlags(QtCore.Qt.ItemIsEnabled)
    # uniquely identifying name is stored in hidden data Qt.UserRole
    item.setData(0, QtCore.Qt.UserRole, ana.Name)
    doc_item.addChild(item)
    item.setExpanded(True)
    return item


def insert_solver_item(
        ana_item: QtGui.QTreeWidgetItem,
        solver: App.DocumentObjectGroup) -> QtGui.QTreeWidgetItem:
    # Insert an item representing a solver to the tree_widget and returns it
    item = QtGui.QTreeWidgetItem()
    item.setText(0, solver.Label)
    item.setIcon(0, solver.ViewObject.Icon)
    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
    # uniquely identifying name is stored in hidden data Qt.UserRole
    item.setData(0, QtCore.Qt.UserRole, solver.Name)
    ana_item.addChild(item)
    return item


def list_documents() -> App.Document:
    return list(App.listDocuments().values())


def list_analysis(doc: App.Document = None) -> List[App.DocumentObjectGroup]:
    # Return a list of the analysis presents in the current document
    if doc is None:
        return App.ActiveDocument.findObjects(Type='Fem::FemAnalysis')
    return doc.findObjects(Type='Fem::FemAnalysis')


def list_solver(ana: App.DocumentObjectGroup):
    # Return a list of solver present in a analysis
    return [sol for sol in ana.Group
            if sol.TypeId == 'Fem::FemSolverObjectPython']


def get_femstate_icon(state: FemState) -> QtGui.QIcon:
    if state is FemState.SETTING_UP:
        return QtGui.QWidget().style().standardIcon(
            QtGui.QStyle.SP_FileIcon)
    elif state is FemState.WRITING:
        return QtGui.QWidget().style().standardIcon(
            QtGui.QStyle.SP_FileIcon)
    elif state is FemState.COMPUTING:
        return QtGui.QWidget().style().standardIcon(
            QtGui.QStyle.SP_ComputerIcon)
    elif state is FemState.FINISHED:
        return QtGui.QWidget().style().standardIcon(
            QtGui.QStyle.SP_DialogApplyButton)
    elif state is FemState.ERROR:
        return QtGui.QWidget().style().standardIcon(
            QtGui.QStyle.SP_MessageBoxCritical)
    elif state is FemState.LOADED:
        return QtGui.QIcon.fromTheme('emblem-downloads')
    else:
        return QtGui.QIcon()


def format_task_output(output: str) -> str:
    # Format the task output so it is well displayed.
    # Indeed, it appears that output returned by qarnot contains "\n"
    # instead of the newline character
    output = output.replace('\\n', '\n')
    return output
