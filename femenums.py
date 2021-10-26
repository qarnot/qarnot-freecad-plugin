from enum import unique, Enum


@unique
class SolverType(Enum):
    UNKNOWN = 0
    CCX_TOOLS = 1
    ELMER = 2
    CCX = 3
    Z88 = 4


@unique
class FemState(Enum):
    SETTING_UP = 0
    WRITING = 1
    COMPUTING = 2
    FINISHED = 3
    ERROR = 4
    LOADED = 5

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented
