"""Browse KDE network places through its existing, authenticated KIO bridge."""
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlsplit, unquote

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from .workers import Job


def network_places(path=None):
    path = path or Path.home() / '.local/share/user-places.xbel'
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    return [(entry.findtext('title') or 'Network', entry.get('href'))
            for entry in root.findall('bookmark')
            if urlsplit(entry.get('href', '')).scheme in {'smb', 'sftp', 'nfs'}]


def resolve_destination(destination):
    parsed = urlsplit(str(destination))
    if not parsed.scheme:
        return Path(destination).expanduser()
    if parsed.scheme == 'file':
        return Path(unquote(parsed.path))
    if parsed.scheme not in {'smb', 'sftp', 'nfs'}:
        raise ValueError('Choose a local folder or an SMB, SFTP or NFS folder.')
    command = shutil.which('qdbus6') or shutil.which('qdbus')
    if not command:
        raise RuntimeError('Mount the NAS in your file manager first, then choose its local folder.')
    try:
        result = subprocess.run(
            [command, 'org.kde.KIOFuse', '/org/kde/KIOFuse',
             'org.kde.KIOFuse.VFS.mountUrl', str(destination)],
            capture_output=True, text=True, timeout=60, check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise RuntimeError('Could not connect to the NAS. Open it in your file manager to check the connection and sign in, then retry.') from exc
    mounted = Path(result.stdout.strip())
    if not mounted.is_absolute() or not mounted.is_dir():
        raise RuntimeError('The NAS did not provide an accessible folder. Reconnect in your file manager and retry.')
    return mounted


class ExportFolderDialog(QFileDialog):
    def __init__(self, destination, parent=None):
        super().__init__(parent, 'Choose export folder')
        self.setOption(QFileDialog.Option.DontUseNativeDialog)
        self.setFileMode(QFileDialog.FileMode.Directory)
        self.setOption(QFileDialog.Option.ShowDirsOnly)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        self.setLabelText(QFileDialog.DialogLabel.Accept, 'Choose')
        self.setMinimumSize(720, 500)
        self.mounts = {}
        self.jobs = set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        self.shortcuts = []
        for title, url in network_places():
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, target=url: self.connect_place(target))
            self.shortcuts.append(button)
            layout.addWidget(button)
        layout.addWidget(self.notice, 1)
        grid = self.layout()
        grid.addWidget(row, grid.rowCount(), 0, 1, grid.columnCount())
        if urlsplit(destination).scheme in {'smb', 'sftp', 'nfs'}:
            self.connect_place(destination)
        else:
            self.setDirectory(destination)

    def connect_place(self, url):
        if self.jobs:
            return
        self.notice.setText('Connecting…')
        for button in self.shortcuts:
            button.setEnabled(False)
        job = Job(resolve_destination, url)
        self.jobs.add(job)

        def ready(path):
            self.mounts[path] = url.rstrip('/')
            self.setDirectory(str(path))
            self.setSidebarUrls(self.sidebarUrls() + [QUrl.fromLocalFile(str(path))])
            self.notice.clear()

        def finished():
            self.jobs.discard(job)
            for button in self.shortcuts:
                button.setEnabled(True)

        job.signals.result.connect(ready)
        job.signals.error.connect(self.notice.setText)
        job.signals.finished.connect(finished)
        self.pool.start(job)

    def destination(self):
        path = Path(self.selectedFiles()[0])
        for mounted, url in sorted(self.mounts.items(), key=lambda item: len(str(item[0])), reverse=True):
            if path.is_relative_to(mounted):
                relative = path.relative_to(mounted).as_posix()
                return url if relative == '.' else url + '/' + quote(relative, safe='/')
        return str(path)

    def accept(self):
        if not self.jobs:
            super().accept()

    def reject(self):
        # Keep the dialog and its signal receivers alive while authentication finishes.
        if self.jobs:
            self.notice.setText('Finishing the connection. You can close this window in a moment.')
            return
        super().reject()
