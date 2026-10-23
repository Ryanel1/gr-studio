"""Native photo workspace: a bounded preview, edits, and local file operations."""

from dataclasses import asdict, replace
from pathlib import Path
from threading import Event

from PySide6.QtCore import QSize, QStandardPaths, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .export_destination import ExportFolderDialog, resolve_destination
from .batch import process_photos
from .frame_panel import FramePanel
from .frames import FRAME_FIELDS
from .geometry import IDENTITY, auto_geometry, guided_matrix
from .geometry_panel import GeometryPanel
from .imaging import (
    EditSettings,
    auto_adjust,
    auto_straighten,
    export_image,
    load_image,
    render,
)
from .import_dialog import ImportDialog
from .state import Library
from .tuning_panel import TuningPanel
from .widgets import Histogram, PhotoView, pil_image
from .workers import Job


class Studio(QMainWindow):
    def __init__(self, data_folder=None):
        super().__init__()
        self.setWindowTitle("GR Studio")
        self.resize(1280, 850)
        self.setMinimumSize(940, 680)
        folder = data_folder or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
        self.library = Library(folder)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self.jobs = set()
        self.path = None
        self.source = None
        self.settings = EditSettings()
        self.loading = False
        self.rendering = False
        self.render_pending = False
        self.revision = 0
        self.comparing = False
        self.exporting = False
        self.geometry_busy = False
        self.batch_busy = False
        self.batch_cancelled = Event()
        self.last_export = None
        self.controls = {}
        self._build()
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(100)
        self.preview_timer.timeout.connect(self.request_preview)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(500)
        self.save_timer.timeout.connect(self.persist_edit)
        for keys, action in [
            ("Ctrl+O", self.open_files),
            ("Ctrl+I", self.open_camera),
            ("Ctrl+E", self.export_current),
            ("Escape", self.cancel_guides),
        ]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(action)
        if self.library.photos:
            self.add_photos(self.library.photos.copy(), save=False)
        self.update_enabled()
        if self.library.error:
            self.status.setText(self.library.error)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar_widget = QWidget()
        toolbar_widget.setObjectName("toolbar")
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(24, 16, 24, 16)
        toolbar.setSpacing(10)
        name = QLabel("GR Studio")
        name.setObjectName("brand")
        toolbar.addWidget(name)
        toolbar.addSpacing(22)
        self.menu_buttons = {}
        self.menus = {}
        for label in ("File", "Edit", "View"):
            button = QToolButton()
            button.setText(label)
            button.setObjectName("menuButton")
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            button.setMenu(menu)
            toolbar.addWidget(button)
            self.menu_buttons[label] = button
            self.menus[label] = menu
        toolbar.addStretch()
        self.open_button = QPushButton("Open photos")
        self.open_button.clicked.connect(self.open_files)
        self.open_button.setToolTip("Open local JPEG, PNG or TIFF photos (Ctrl+O)")
        toolbar.addWidget(self.open_button)
        self.usb_button = QPushButton("Import from USB")
        self.usb_button.clicked.connect(self.open_camera)
        self.usb_button.setToolTip("Browse the connected GR IV (Ctrl+I)")
        toolbar.addWidget(self.usb_button)
        layout.addWidget(toolbar_widget)
        split = QSplitter(Qt.Orientation.Horizontal)
        main = QWidget()
        main.setObjectName("canvas")
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        image_bar = QHBoxLayout()
        image_bar.setContentsMargins(20, 10, 20, 10)
        self.filename = QLabel("No photo selected")
        self.filename.setObjectName("muted")
        self.filename.setMinimumWidth(0)
        self.filename.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        image_bar.addWidget(self.filename, 1)
        self.compare = QPushButton("Compare")
        self.compare.setObjectName("quiet")
        self.compare.setToolTip(
            "Hold to see the original photo without edits or border"
        )
        self.compare.pressed.connect(self.compare_start)
        self.compare.released.connect(self.compare_end)
        image_bar.addWidget(self.compare)
        main_layout.addLayout(image_bar)
        self.view = PhotoView()
        main_layout.addWidget(self.view, 1)
        strip_bar = QHBoxLayout()
        strip_bar.setContentsMargins(20, 8, 20, 8)
        strip_bar.setSpacing(8)
        self.library_label = QLabel("Session")
        self.library_label.setObjectName("muted")
        strip_bar.addWidget(self.library_label)
        strip_bar.addStretch()
        self.select_all = QPushButton("Select all")
        self.select_all.setObjectName("quiet")
        self.select_all.clicked.connect(lambda: self.filmstrip.selectAll())
        strip_bar.addWidget(self.select_all)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("quiet")
        self.remove_button.setToolTip(
            "Remove from this workspace; the file stays on disk"
        )
        self.remove_button.clicked.connect(self.remove_current)
        strip_bar.addWidget(self.remove_button)
        main_layout.addLayout(strip_bar)
        self.filmstrip = QListWidget()
        self.filmstrip.setObjectName("filmstrip")
        self.filmstrip.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.filmstrip.setToolTip(
            "Ctrl-click (Command-click on Mac) to select photos; Shift-click for a range."
        )
        self.filmstrip.itemSelectionChanged.connect(self.update_enabled)
        self.filmstrip.setFlow(QListWidget.Flow.LeftToRight)
        self.filmstrip.setWrapping(False)
        self.filmstrip.setViewMode(QListWidget.ViewMode.IconMode)
        self.filmstrip.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.filmstrip.setMovement(QListWidget.Movement.Static)
        self.filmstrip.setIconSize(QSize(110, 76))
        self.filmstrip.setGridSize(QSize(140, 114))
        self.filmstrip.setFixedHeight(148)
        self.filmstrip.setAccessibleName("Photo filmstrip")
        self.filmstrip.currentItemChanged.connect(self.select_photo)
        main_layout.addWidget(self.filmstrip)
        split.addWidget(main)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(340)
        scroll.setMaximumWidth(460)
        panel = QWidget()
        controls = QVBoxLayout(panel)
        controls.setContentsMargins(24, 24, 24, 24)
        controls.setSpacing(16)
        title = QLabel("Develop")
        title.setObjectName("title")
        inspector_heading = QHBoxLayout()
        inspector_heading.addWidget(title)
        inspector_heading.addStretch()
        controls.addLayout(inspector_heading)
        self.adjustment_panel = QWidget()
        adjustment_layout = QVBoxLayout(self.adjustment_panel)
        adjustment_layout.setContentsMargins(0, 0, 0, 0)
        adjustment_layout.setSpacing(24)
        self.tabs = QTabWidget()
        adjustment_layout.addWidget(self.tabs)
        edit_panel = QWidget()
        al = QVBoxLayout(edit_panel)
        al.setContentsMargins(0, 20, 0, 8)
        al.setSpacing(12)
        self.frame_panel = FramePanel()
        self.frame_panel.changed.connect(self.change_setting)
        self.frame_panel.apply_requested.connect(self.apply_frame)
        self.border = self.frame_panel.border
        self.paper = self.frame_panel.paper
        self.caption = self.frame_panel.caption
        self.apply_frame_button = self.frame_panel.apply_button
        self.tabs.addTab(edit_panel, "Adjust")
        self.histogram = Histogram()
        al.addWidget(self.histogram)
        self.auto_adjust_button = QPushButton("Auto adjust")
        self.auto_adjust_button.setObjectName("primary")
        self.auto_adjust_button.setToolTip(
            "Adjust each selected photo individually. Sliders change only the previewed photo."
        )
        self.auto_adjust_button.clicked.connect(self.apply_auto_adjust)
        al.addWidget(self.auto_adjust_button)
        self.tabs.addTab(self.frame_panel, "Frame")
        self.geometry_panel = GeometryPanel()
        self.geometry_panel.apply_requested.connect(self.apply_upright)
        self.geometry_panel.mode_changed.connect(self.geometry_mode_changed)
        self.geometry_panel.changed.connect(self.change_setting)
        self.geometry_panel.guide_direction.connect(self.set_guide_direction)
        self.geometry_panel.undo_requested.connect(self.view.undo_guide)
        self.geometry_panel.cancel_requested.connect(self.cancel_guides)
        self.geometry_panel.reset_requested.connect(self.reset_geometry)
        self.view.guides_changed.connect(self.guides_changed)
        self.controls.update(self.geometry_panel.controls)
        self.auto_button = self.geometry_panel.apply
        self.angle_info = self.geometry_panel.message
        self.tabs.addTab(self.geometry_panel, "Straighten")
        self.tuning_panel = TuningPanel()
        self.tuning_panel.changed.connect(self.change_setting)
        self.controls.update(self.tuning_panel.controls)
        al.addWidget(self.tuning_panel)
        al.addStretch()
        self.reset = QPushButton("Reset")
        self.reset.setObjectName("quiet")
        self.reset.clicked.connect(self.reset_edits)
        self.reset.setToolTip("Reset all edits for the previewed photo")
        inspector_heading.addWidget(self.reset)

        def size_active_tab(index):
            for i in range(self.tabs.count()):
                page = self.tabs.widget(i)
                page.setSizePolicy(
                    QSizePolicy.Policy.Preferred,
                    QSizePolicy.Policy.Preferred
                    if i == index
                    else QSizePolicy.Policy.Ignored,
                )
                page.updateGeometry()
            self.tabs.updateGeometry()

        self.tabs.currentChanged.connect(size_active_tab)
        size_active_tab(0)
        controls.addWidget(self.adjustment_panel)
        controls.addStretch()
        footer = QWidget()
        footer.setObjectName("exportFooter")
        export_layout = QVBoxLayout(footer)
        export_layout.setContentsMargins(24, 20, 24, 24)
        export_layout.setSpacing(12)
        self.export_button = QPushButton("Export to folder…")
        self.export_button.setObjectName("primary")
        self.export_button.clicked.connect(self.export_current)
        export_layout.addWidget(self.export_button)
        self.batch_progress = QProgressBar()
        self.batch_progress.hide()
        export_layout.addWidget(self.batch_progress)
        self.cancel_batch = QPushButton("Stop after this photo")
        self.cancel_batch.clicked.connect(self.batch_cancelled.set)
        self.cancel_batch.hide()
        export_layout.addWidget(self.cancel_batch)
        self.reveal = QPushButton("Show export folder")
        self.reveal.clicked.connect(self.reveal_export)
        self.reveal.hide()
        export_layout.addWidget(self.reveal)
        scroll.setWidget(panel)
        sidebar = QWidget()
        sidebar.setMinimumWidth(360)
        sidebar.setMaximumWidth(460)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(scroll, 1)
        sidebar_layout.addWidget(footer)
        split.addWidget(sidebar)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([880, 400])
        layout.addWidget(split, 1)
        self.status = QLabel("Ready")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._build_menus()

    def _build_menus(self):
        self.menu_actions = []

        def action(menu, title, button):
            item = self.menus[menu].addAction(title)
            item.triggered.connect(button.click)
            self.menu_actions.append((item, button))
            return item

        action("File", "Open photos…", self.open_button)
        action("File", "Import from USB…", self.usb_button)
        self.menus["File"].addSeparator()
        action("File", "Export selected…", self.export_button)
        self.menus["File"].addSeparator()
        self.menus["File"].addAction("Close window", self.close)
        action("Edit", "Auto adjust selected", self.auto_adjust_button)
        action("Edit", "Apply border to selected", self.apply_frame_button)
        self.menus["Edit"].addSeparator()
        action("Edit", "Reset photo", self.reset)
        action("Edit", "Select all photos", self.select_all)
        action("Edit", "Remove from session", self.remove_button)
        for index, label in enumerate(("Adjust", "Frame", "Straighten")):
            item = self.menus["View"].addAction(label)
            item.triggered.connect(
                lambda checked=False, i=index: self.tabs.setCurrentIndex(i)
            )
        self.menus["View"].addSeparator()
        item = self.menus["View"].addAction("Filmstrip")
        item.setCheckable(True)
        item.setChecked(True)
        item.toggled.connect(self.filmstrip.setVisible)
        for menu in self.menus.values():
            menu.aboutToShow.connect(self._sync_menus)

    def _sync_menus(self):
        for action, button in self.menu_actions:
            action.setEnabled(button.isEnabled())

    def job(self, function, result, final=None, error=None, priority=0):
        job = Job(function)
        self.jobs.add(job)
        job.signals.result.connect(result)
        job.signals.error.connect(error or self.show_error)

        def finished():
            self.jobs.discard(job)
            if final:
                final()

        job.signals.finished.connect(finished)
        self.pool.start(job, priority)
        return job

    def show_error(self, error):
        self.status.setText(f"Could not complete the operation: {error}")

    def selected_paths(self):
        return [
            self.filmstrip.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.filmstrip.count())
            if self.filmstrip.item(i).isSelected()
        ]

    def update_enabled(self):
        ready = (
            self.source is not None
            and not self.loading
            and not self.batch_busy
            and not self.geometry_busy
        )
        guiding = self.view.guiding
        locked = self.batch_busy or self.geometry_busy or guiding
        self.menu_buttons["View"].setEnabled(not locked)
        count = len(self.selected_paths())
        self.adjustment_panel.setEnabled(ready)
        self.reset.setEnabled(ready and not guiding)
        self.compare.setEnabled(ready and not guiding)
        self.export_button.setEnabled(ready and count > 0 and not guiding)
        self.remove_button.setEnabled(ready and not guiding)
        self.filmstrip.setEnabled(not locked)
        self.tabs.tabBar().setEnabled(not guiding)
        self.select_all.setEnabled(not locked and self.filmstrip.count() > 0)
        self.open_button.setEnabled(not locked)
        self.usb_button.setEnabled(not locked)
        self.auto_adjust_button.setEnabled(ready and count > 0)
        self.auto_adjust_button.setText(
            f"Auto adjust {count} photos" if count > 1 else "Auto adjust"
        )
        self.export_button.setText(
            f"Export {count} photos…" if count > 1 else "Export to folder…"
        )
        self.apply_frame_button.setText(f"Apply border to {count} selected")
        self.apply_frame_button.setEnabled(ready and count > 1)
        self.apply_frame_button.setVisible(count > 1)
        self.library_label.setText(
            f"{self.filmstrip.count()} {'photo' if self.filmstrip.count() == 1 else 'photos'} · {count} selected"
        )
        self.frame_panel.update_state(self.settings, ready)
        self.geometry_panel.guide_state(guiding, self.view.guides)

    def selection_snapshot(self):
        self.persist_edit()
        self.save_timer.stop()
        return [(path, self.library.settings(path)) for path in self.selected_paths()]

    def run_batch(self, label, items, operation, result):
        self.batch_busy = True
        self.batch_cancelled.clear()
        self.update_enabled()
        self.batch_progress.setRange(0, len(items))
        self.batch_progress.setValue(0)
        self.batch_progress.show()
        self.cancel_batch.show()
        job = Job(
            lambda: process_photos(
                items, operation, job.signals.progress.emit, self.batch_cancelled
            )
        )
        self.jobs.add(job)

        def progress(value):
            done, total, path = value
            self.batch_progress.setValue(done)
            self.status.setText(f"{label} · {done}/{total} · {Path(path).name}")

        def finished():
            self.jobs.discard(job)
            self.batch_busy = False
            self.exporting = False
            self.batch_progress.hide()
            self.cancel_batch.hide()
            self.update_enabled()

        job.signals.progress.connect(progress)
        job.signals.result.connect(result)
        job.signals.error.connect(self.show_error)
        job.signals.finished.connect(finished)
        self.pool.start(job)

    def batch_message(self, label, results, errors, stopped):
        message = f"{label}: {len(results)} photo(s)."
        if stopped:
            message += " Stopped; completed photos were kept."
        if errors:
            message += f" {len(errors)} failed: " + "; ".join(
                f"{Path(p).name}: {e}" for p, e in errors
            )
        self.status.setText(message)

    def apply_frame(self):
        if self.source is None or self.batch_busy:
            return
        items = self.selection_snapshot()
        for path, settings in items:
            self.library.edits[path] = asdict(
                replace(
                    settings,
                    **{key: getattr(self.settings, key) for key in FRAME_FIELDS},
                )
            )
        try:
            self.library.save()
            self.status.setText(
                f"Border applied to {len(items)} photos. Each keeps its own caption and adjustments."
            )
        except OSError as exc:
            self.show_error(str(exc))

    def open_files(self):
        if self.batch_busy or self.geometry_busy or self.view.guiding:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open photos",
            self.library.import_folder,
            "Photos (*.jpg *.jpeg *.JPG *.JPEG *.png *.PNG *.tif *.tiff *.TIF *.TIFF)",
        )
        if paths:
            self.add_photos(paths)

    def add_photos(self, paths, save=True):
        existing = {
            self.filmstrip.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.filmstrip.count())
        }
        raw = 0
        for path in paths:
            path = str(Path(path).resolve())
            if Path(path).suffix.lower() == ".dng":
                raw += 1
                continue
            if path in existing:
                continue
            existing.add(path)
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.filmstrip.addItem(item)
            if path not in self.library.photos:
                self.library.photos.append(path)

            def thumb_ready(image, item=item):
                if self.filmstrip.row(item) >= 0:
                    item.setIcon(QIcon(QPixmap.fromImage(pil_image(image))))

            self.job(lambda path=path: load_image(path, 220), thumb_ready, priority=-1)
        self.library_label.setText(f"Session · {self.filmstrip.count()}")
        if save:
            try:
                self.library.save()
            except OSError as exc:
                self.show_error(str(exc))
        if self.filmstrip.currentRow() < 0 and self.filmstrip.count():
            self.filmstrip.setCurrentRow(0)
        if raw:
            self.status.setText(
                f"{raw} DNG file(s) saved to your import folder. Open the matching JPEG to edit."
            )

    def select_photo(self, current, previous=None):
        self.view.stop_guides()
        self.persist_edit()
        self.save_timer.stop()
        self.revision += 1
        self.source = None
        self.histogram.set_image(None)
        self.comparing = False
        if current is None:
            self.path = None
            self.view.set_image(None)
            self.filename.setText("No photo selected")
            self.update_enabled()
            return
        self.path = current.data(Qt.ItemDataRole.UserRole)
        path = self.path
        self.settings = self.library.settings(path)
        self.sync_controls()
        self.loading = True
        self.view.set_image(None)
        self.view.message = "Loading photo…"
        self.view.detail = Path(path).name
        self.filename.setText(Path(path).name)
        self.update_enabled()

        def loaded(image):
            if self.path != path:
                return
            self.source = image
            self.histogram.set_image(image)
            self.loading = False
            self.view.message = "Your next print starts here."
            self.view.detail = "Import from your GR IV, or open photos from a folder."
            self.status.setText("Ready")
            self.update_enabled()
            self.request_preview()

        def failed(error):
            if self.path == path:
                self.loading = False
                self.view.message = "This photo could not be opened."
                self.view.detail = error
                self.view.update()
                self.update_enabled()
                self.show_error(error)

        self.job(lambda: load_image(path, 1400), loaded, error=failed, priority=1)

    def sync_controls(self):
        for name, control in self.controls.items():
            control.set_value(getattr(self.settings, name))
        self.tuning_panel.sync(self.settings)
        self.frame_panel.sync(self.settings)
        self.geometry_panel.sync(self.settings)
        self.angle_info.clear()
        self.angle_info.hide()

    def change_setting(self, key, value):
        if self.source is None:
            return
        self.settings = replace(self.settings, **{key: value})
        self.revision += 1
        self.preview_timer.start()
        self.save_timer.start()
        self.update_enabled()

    def persist_edit(self):
        if self.path and self.source is not None:
            try:
                self.library.save_edit(self.path, self.settings)
            except OSError as exc:
                self.show_error(f"Edits could not be saved: {exc}")

    def request_preview(self):
        if self.source is None or self.view.guiding:
            return
        if self.rendering:
            self.render_pending = True
            return
        self.rendering = True
        self.render_pending = False
        source, settings, revision, path = (
            self.source,
            replace(self.settings),
            self.revision,
            self.path,
        )

        def rendered(image):
            if (
                revision == self.revision
                and path == self.path
                and not self.comparing
                and not self.view.guiding
            ):
                self.view.set_image(image)

        def finished():
            self.rendering = False
            if self.render_pending:
                self.request_preview()

        self.job(lambda: render(source, settings, preview=True), rendered, finished)

    def compare_start(self):
        if self.source is not None:
            self.comparing = True
            self.view.set_image(self.source)

    def compare_end(self):
        self.comparing = False
        self.request_preview()

    def apply_auto_adjust(self):
        if self.source is None or self.batch_busy:
            return
        items = self.selection_snapshot()
        if not items:
            return

        def adjust(path, settings):
            return replace(settings, **auto_adjust(load_image(path, 1400)))

        def result(value):
            results, errors, stopped = value
            for path, settings in results:
                self.library.edits[path] = asdict(settings)
            if any(path == self.path for path, _ in results):
                self.settings = self.library.settings(self.path)
                self.revision += 1
                self.sync_controls()
                self.request_preview()
            self.batch_message("Auto adjustments applied", results, errors, stopped)
            try:
                self.library.save()
            except OSError as exc:
                self.show_error(f"Edits could not be saved: {exc}")

        self.run_batch("Auto adjusting", items, adjust, result)

    def set_guide_direction(self, direction):
        self.view.guide_kind = direction
        if self.view.guiding:
            self.status.setText(
                f"Draw two {direction} guides along separate straight edges. Esc cancels."
            )

    def guides_changed(self):
        self.geometry_panel.guide_state(self.view.guiding, self.view.guides)
        if self.view.guiding:
            self.status.setText(
                "Draw two vertical or two horizontal guides; optionally add a second pair. Apply guides when ready."
            )

    def geometry_mode_changed(self, mode):
        if self.view.guiding:
            self.view.stop_guides()
            self.request_preview()
        if mode == "guided" and self.source is not None:
            self.begin_guides()
        else:
            self.update_enabled()

    def begin_guides(self):
        if self.source is None or self.batch_busy or self.geometry_busy:
            return
        self.revision += 1
        self.view.guide_kind = self.geometry_panel.direction.currentData()
        self.view.start_guides(self.source)
        self.update_enabled()

    def cancel_guides(self):
        if not self.view.guiding:
            return
        self.view.stop_guides()
        self.geometry_panel.sync(self.settings)
        self.update_enabled()
        self.request_preview()
        self.status.setText("Guides cancelled; previous geometry kept.")

    def set_geometry(self, matrix, mode, angle=0.0):
        self.settings = replace(
            self.settings,
            geometry=matrix,
            geometry_mode=mode,
            vertical=0.0,
            horizontal=0.0,
            aspect=0.0,
            angle=angle,
        )
        self.revision += 1
        self.sync_controls()
        self.update_enabled()
        self.request_preview()
        self.persist_edit()

    def reset_geometry(self):
        self.set_geometry(IDENTITY, "off")
        self.status.setText("Geometry reset.")

    def apply_upright(self):
        if self.source is None or self.batch_busy or self.geometry_busy:
            return
        mode = self.geometry_panel.mode.currentData()
        if mode == "off":
            self.reset_geometry()
        elif mode == "guided":
            if not self.view.guiding:
                self.begin_guides()
                return
            try:
                matrix = guided_matrix(self.view.guides, self.source.size)
            except ValueError as exc:
                self.status.setText(str(exc))
                return
            self.view.stop_guides()
            self.set_geometry(matrix, "guided")
            self.status.setText("Guided correction applied.")
        else:
            self.run_upright(mode)

    def straighten(self):
        self.run_upright("level")

    def run_upright(self, mode):
        if (
            self.source is None
            or self.geometry_busy
            or self.batch_busy
            or self.view.guiding
        ):
            return
        source, path, revision = self.source, self.path, self.revision
        self.geometry_busy = True
        self.update_enabled()
        self.status.setText(f"Analyzing {mode} geometry…")

        def analyze():
            if mode == "level":
                angle, reason = auto_straighten(source)
                if "manually" in reason.lower():
                    raise ValueError(reason)
                return IDENTITY, round(angle, 1)
            return auto_geometry(source, mode), 0.0

        def result(value):
            if self.path != path or self.revision != revision:
                return
            matrix, angle = value
            self.set_geometry(matrix, mode, angle)
            self.status.setText(f"{mode.title()} correction applied.")

        def failed(error):
            self.status.setText(error)

        def finished():
            self.geometry_busy = False
            self.update_enabled()

        self.job(analyze, result, finished, failed)

    def reset_edits(self):
        if self.source is None:
            return
        self.settings = EditSettings()
        self.revision += 1
        self.sync_controls()
        self.update_enabled()
        self.request_preview()
        self.persist_edit()

    def remove_current(self):
        if self.path is None:
            return
        path = self.path
        self.persist_edit()
        self.library.photos = [p for p in self.library.photos if p != path]
        item = self.filmstrip.takeItem(self.filmstrip.currentRow())
        # Keep item alive until thumbnail jobs finish; Qt will own other items.
        self._removed_item = item
        self.library_label.setText(f"Session · {self.filmstrip.count()}")
        try:
            self.library.save()
        except OSError as exc:
            self.show_error(str(exc))

    def open_camera(self):
        if self.batch_busy or self.geometry_busy or self.view.guiding:
            return
        self.camera_dialog = ImportDialog(self.library, self)
        self.camera_dialog.imported.connect(self.add_photos)
        self.camera_dialog.open()
        self.camera_dialog.scan_camera()

    def export_current(self):
        if (
            self.source is None
            or self.batch_busy
            or self.geometry_busy
            or self.view.guiding
        ):
            return
        dialog = ExportFolderDialog(self.library.export_folder, self)
        if dialog.exec():
            self.export_to(dialog.destination())

    def export_to(self, folder):
        if (
            not self.path
            or self.source is None
            or self.batch_busy
            or self.geometry_busy
            or self.view.guiding
        ):
            return
        self.library.export_folder = str(folder)
        items = self.selection_snapshot()
        if not items:
            return
        self.exporting = True

        def result(value):
            results, errors, stopped = value
            if results:
                self.last_export = results[-1][1]
                self.reveal.show()
            self.batch_message(f"Exported to {folder}", results, errors, stopped)

        resolved = None
        connection_error = None

        def export_one(path, settings):
            nonlocal resolved, connection_error
            if connection_error is not None:
                raise connection_error
            if resolved is None:
                try:
                    resolved = resolve_destination(folder)
                except Exception as exc:
                    connection_error = exc
                    raise
            return export_image(path, settings, resolved)

        self.run_batch("Exporting", items, export_one, result)

    def reveal_export(self):
        if self.last_export:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_export.parent)))

    def closeEvent(self, event):
        if self.jobs or (
            getattr(self, "camera_dialog", None) and self.camera_dialog.jobs
        ):
            self.status.setText(
                "Finishing the current operation. Please close the window again in a moment."
            )
            event.ignore()
            return
        self.persist_edit()
        event.accept()
