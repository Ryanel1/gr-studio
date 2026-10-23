"""USB photo chooser. Camera calls run off the UI thread and are read-only."""

from pathlib import Path
from threading import Event

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from . import camera
from .workers import Job


class ImportDialog(QDialog):
    imported = Signal(object)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self.files = []
        self.jobs = set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.cancel = Event()
        self.busy = False
        self.thumb_cursor = 0
        self.thumbnail_running = False
        self.thumbnail_attempted = set()
        self.pending_import = False
        self.closing = False
        self.setWindowTitle("Import from GR IV")
        self.resize(1040, 760)
        self.setMinimumSize(780, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        title = QLabel("Import from GR IV")
        title.setObjectName("title")
        heading = QHBoxLayout()
        heading.addWidget(title)
        heading.addStretch()
        layout.addLayout(heading)
        self.status = QLabel("Ready to scan")
        self.status.setToolTip("Connect your GR IV with a USB-C data cable, then scan.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.scan = QPushButton("Scan camera")
        self.scan.clicked.connect(self.scan_camera)
        top.addWidget(self.scan)
        self.select = QPushButton("Select JPEGs")
        self.select.setObjectName("quiet")
        self.select.clicked.connect(self.select_jpegs)
        top.addWidget(self.select)
        self.clear = QPushButton("Clear selection")
        self.clear.setObjectName("quiet")
        self.clear.clicked.connect(self.clear_selection)
        top.addWidget(self.clear)
        top.addStretch()
        self.thumbs = QPushButton("Retry previews")
        self.thumbs.setObjectName("quiet")
        self.thumbs.clicked.connect(self.load_thumbnails)
        top.addWidget(self.thumbs)
        layout.addLayout(top)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Photo", "Storage", "Format", "Size"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setAccessibleName("Camera photos; check photos to import")
        self.table.setColumnWidth(1, 95)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 105)
        self.table.setIconSize(QSize(160, 120))
        self.table.verticalScrollBar().valueChanged.connect(self.queue_thumbnails)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self.selection_changed)
        layout.addWidget(self.table, 1)
        self.folder = QPushButton("Choose folder…")
        self.folder_name = QLabel()
        self.folder_name.setObjectName("muted")
        self.folder_name.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._show_folder()
        self.folder.clicked.connect(self.choose_folder)
        destination = QHBoxLayout()
        destination.setSpacing(16)
        destination.addWidget(QLabel("Destination"))
        destination.addWidget(self.folder_name, 1)
        destination.addWidget(self.folder)
        layout.addLayout(destination)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        foot = QHBoxLayout()
        self.count = QLabel("0 selected")
        self.count.setObjectName("muted")
        foot.addWidget(self.count)
        foot.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        foot.addWidget(self.close_button)
        self.start = QPushButton("Import selected")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.import_selected)
        foot.addWidget(self.start)
        layout.addLayout(foot)
        self._controls()

    def _show_folder(self):
        path = Path(self.library.import_folder)
        self.folder_name.setText(path.name or str(path))
        self.folder_name.setToolTip(str(path))
        self.folder.setToolTip(str(path))

    def _job(self, fn, result, progress=None):
        job = Job(fn)
        self.jobs.add(job)
        job.signals.result.connect(result)
        job.signals.error.connect(self.show_error)
        job.signals.finished.connect(lambda: self._finished(job))
        if progress:
            job.signals.progress.connect(progress)
        self.pool.start(job)
        return job

    def _finished(self, job):
        self.jobs.discard(job)
        self.busy = False
        self.progress.hide()
        self.close_button.setText("Close")
        self._controls()
        self.queue_thumbnails()

    def _controls(self):
        self.scan.setEnabled(not self.busy and not self.thumbnail_running)
        self.folder.setEnabled(not self.busy)
        self.select.setEnabled(not self.busy and bool(self.files))
        self.clear.setEnabled(not self.busy and bool(self.files))
        self.thumbs.setEnabled(
            not self.busy
            and not self.thumbnail_running
            and bool(self.thumbnail_attempted)
        )
        self.start.setEnabled(not self.busy and bool(self.selected()))
        self.table.setEnabled(not self.busy)

    def selected(self):
        return [
            f
            for i, f in enumerate(self.files)
            if self.table.item(i, 0).checkState() == Qt.CheckState.Checked
        ]

    def selection_changed(self):
        chosen = self.selected()
        self.count.setText(
            f"{len(chosen)} selected · {sum(f.size for f in chosen) / 1_000_000:.1f} MB"
        )
        self._controls()

    def select_jpegs(self):
        self.table.blockSignals(True)
        for i, f in enumerate(self.files):
            self.table.item(i, 0).setCheckState(
                Qt.CheckState.Checked
                if Path(f.name).suffix.lower() in (".jpg", ".jpeg")
                else Qt.CheckState.Unchecked
            )
        self.table.blockSignals(False)
        self.selection_changed()

    def clear_selection(self):
        self.table.blockSignals(True)
        for i in range(len(self.files)):
            self.table.item(i, 0).setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.selection_changed()

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose import folder", self.library.import_folder
        )
        if folder:
            self.library.import_folder = folder
            self._show_folder()
            try:
                self.library.save()
            except OSError as exc:
                self.show_error(str(exc))

    def scan_camera(self):
        if self.thumbnail_running:
            return
        self.closing = False
        self.busy = True
        self.status.setText("Reading the camera…")
        self._controls()
        self.progress.setRange(0, 0)
        self.progress.show()
        self._job(camera.list_files, self.populate)

    def populate(self, files):
        self.table.blockSignals(True)
        self.files = files
        self.thumb_cursor = 0
        self.thumbnail_attempted.clear()
        self.table.setRowCount(len(files))
        for row, f in enumerate(files):
            item = QTableWidgetItem(f.name)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, item)
            for col, text in enumerate(
                [
                    f.storage,
                    Path(f.name).suffix[1:].upper(),
                    f"{f.size / 1_000_000:.1f} MB",
                ],
                1,
            ):
                self.table.setItem(row, col, QTableWidgetItem(text))
            self.table.setRowHeight(row, 144)
        self.table.blockSignals(False)
        self.status.setText(
            f"{len(files)} photos"
            if files
            else "The camera is connected, but no JPEG or DNG files were found. Check the camera storage selection."
        )
        self.selection_changed()
        self.queue_thumbnails()

    def queue_thumbnails(self, *_):
        QTimer.singleShot(0, self._next_thumbnail)

    def load_thumbnails(self):
        """Retry missing previews; normal loading is automatic and viewport-first."""
        self.thumbnail_attempted = {
            row
            for row in self.thumbnail_attempted
            if not self.table.item(row, 0).icon().isNull()
        }
        self.queue_thumbnails()

    def _next_thumbnail(self):
        if (
            self.busy
            or self.thumbnail_running
            or self.closing
            or not self.files
            or not self.isVisible()
        ):
            return
        top = max(0, self.table.rowAt(0))
        bottom = self.table.rowAt(self.table.viewport().height() - 1)
        if bottom < 0:
            bottom = len(self.files) - 1
        rows = range(top, min(len(self.files), bottom + 2))
        row = next((r for r in rows if r not in self.thumbnail_attempted), None)
        if row is None:
            return
        self.thumbnail_attempted.add(row)
        self.thumbnail_running = True
        file = self.files[row]
        self.table.item(row, 0).setToolTip(f"Loading preview for {file.name}…")
        job = Job(camera.thumbnail, file, self.library.folder / "thumbnails")
        self.jobs.add(job)
        job.signals.result.connect(lambda path: self.show_thumbnail(row, path))
        job.signals.error.connect(lambda error: self.show_thumbnail(row, None))
        job.signals.finished.connect(lambda: self._thumbnail_finished(job))
        self._controls()
        self.pool.start(job)

    def show_thumbnail(self, row, path):
        item = self.table.item(row, 0)
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap))
            item.setToolTip(self.files[row].name)
        else:
            item.setText(self.files[row].name + "\nPreview unavailable")
            item.setToolTip(
                "The camera did not provide a preview. Click Retry previews to try again."
            )

    def _thumbnail_finished(self, job):
        self.jobs.discard(job)
        self.thumbnail_running = False
        if self.closing:
            super().reject()
            return
        if self.pending_import:
            self.pending_import = False
            self.busy = False
            self.import_selected()
            return
        self._controls()
        self.queue_thumbnails()

    def import_selected(self):
        if self.thumbnail_running:
            self.pending_import = True
            self.busy = True
            self._controls()
            self.status.setText(
                "Finishing the current preview, then importing your selection…"
            )
            return
        selected = self.selected()
        if not selected:
            return
        self.busy = True
        self.cancel.clear()
        self._controls()
        self.progress.setRange(0, len(selected))
        self.progress.setValue(0)
        self.progress.show()
        self.close_button.setText("Stop after current photo")
        self.status.setText(f"Importing {len(selected)} files…")
        folder = self.library.import_folder
        job = Job(lambda: None)

        def work():
            paths = []
            errors = []
            for f in selected:
                if self.cancel.is_set():
                    break
                try:
                    path = camera.download(f, folder)
                    paths.append(path)
                    job.signals.progress.emit((path, len(paths)))
                except Exception as exc:
                    errors.append(f"{f.name}: {exc}")
                    break
            return paths, errors

        job.function = work
        self.jobs.add(job)
        job.signals.progress.connect(lambda v: self.import_progress(v, len(selected)))
        job.signals.result.connect(self.import_done)
        job.signals.error.connect(self.show_error)
        job.signals.finished.connect(lambda: self._finished(job))
        self.pool.start(job)

    def import_progress(self, value, total):
        path, count = value
        self.progress.setValue(count)
        self.status.setText(f"Imported {count} of {total}: {path.name}")
        self.imported.emit([path])

    def import_done(self, result):
        paths, errors = result
        message = f"{len(paths)} files imported to {self.library.import_folder}."
        if self.cancel.is_set():
            message += " Import stopped."
        if errors:
            message += "\n" + errors[0]
        self.status.setText(message)

    def show_error(self, error):
        self.status.setText(error)

    def reject(self):
        if self.thumbnail_running:
            self.closing = True
            self.pending_import = False
            self.status.setText("Closing after the current preview finishes…")
            return
        if self.busy:
            self.cancel.set()
            self.status.setText(
                "Finishing the current camera operation before stopping…"
            )
            return
        super().reject()

    def closeEvent(self, event):
        if self.busy or self.thumbnail_running:
            self.reject()
            event.ignore()
        else:
            event.accept()
