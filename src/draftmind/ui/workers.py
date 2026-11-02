"""Ejecución de tareas lentas (red, disco) fuera del hilo de la interfaz.

Qt solo permite tocar los widgets desde el hilo principal. La tarea corre en
un hilo del QThreadPool y comunica el resultado mediante señales, que Qt
entrega de forma segura en el hilo principal.
"""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Signals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)


class Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], with_progress: bool):
        super().__init__()
        self.fn = fn
        self.with_progress = with_progress
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(self.signals.progress.emit) if self.with_progress else self.fn()
        except Exception as exc:  # Cualquier fallo se muestra en la interfaz.
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.signals.finished.emit(result)


_running: set[Task] = set()  # Evita que Python libere la tarea mientras corre.


def run_task(
    fn: Callable[..., Any],
    on_done: Callable[[Any], None],
    on_error: Callable[[str], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> Task:
    """Ejecuta ``fn`` en segundo plano. Si se pasa ``on_progress``, ``fn``
    recibe como argumento una función ``progress(hecho, total)``."""
    task = Task(fn, with_progress=on_progress is not None)
    _running.add(task)
    task.signals.finished.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    if on_progress:
        task.signals.progress.connect(on_progress)
    task.signals.finished.connect(lambda _: _running.discard(task))
    task.signals.failed.connect(lambda _: _running.discard(task))
    QThreadPool.globalInstance().start(task)
    return task
