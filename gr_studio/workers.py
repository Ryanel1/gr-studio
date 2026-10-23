"""Small thread-pool jobs; UI callbacks always run on the Qt main thread."""

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    progress = Signal(object)


class Job(QRunnable):
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function, self.args, self.kwargs = function, args, kwargs
        self.signals = Signals()

    @Slot()
    def run(self):
        try:
            self.signals.result.emit(self.function(*self.args, **self.kwargs))
        except Exception as exc:
            self.signals.error.emit(str(exc) or type(exc).__name__)
        finally:
            self.signals.finished.emit()
