"""Export to network folders.

Linux (KDE): saved network places are mounted through the authenticated KIO
Fuse bridge. macOS: volumes mounted in Finder appear under /Volumes; a
remembered network URL is re-mounted through Finder ("open smb://…") when the
volume is not currently mounted.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlsplit, unquote

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget

from .workers import Job

PLATFORM = sys.platform
NETWORK_SCHEMES = {'smb', 'sftp', 'nfs'}
MOUNT_WAIT = 60      # seconds to wait for Finder to finish mounting
MOUNT_POLL = 1.0     # seconds between checks while waiting
# macOS `mount` lines: "//user@host/share on /Volumes/share (smbfs, nodev, …)"
# or "host:/export on /Volumes/export (nfs, nodev, …)".
_MOUNT_LINE = re.compile(r'^(?P<source>.+?) on (?P<point>/.+?) \((?P<kind>smbfs|nfs)[,)]')


def network_places(path=None):
    path = path or Path.home() / '.local/share/user-places.xbel'
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    return [(entry.findtext('title') or 'Network', entry.get('href'))
            for entry in root.findall('bookmark')
            if urlsplit(entry.get('href', '')).scheme in NETWORK_SCHEMES]


def mounted_volumes(output=None):
    """macOS: {mount point: network URL} for SMB and NFS volumes Finder has mounted."""
    if output is None:
        if PLATFORM != 'darwin':
            return {}
        try:
            output = subprocess.run(['mount'], capture_output=True, text=True,
                                    timeout=10, check=True).stdout
        except (subprocess.SubprocessError, OSError):
            return {}
    volumes = {}
    for line in output.splitlines():
        match = _MOUNT_LINE.match(line)
        if not match:
            continue
        source, point, kind = match.group('source', 'point', 'kind')
        if kind == 'smbfs' and source.startswith('//'):
            netloc, _, share = source[2:].partition('/')
            volumes[Path(point)] = f'smb://{netloc}/{quote(unquote(share))}'
        elif kind == 'nfs' and ':/' in source:
            host, _, export = source.partition(':')
            volumes[Path(point)] = f'nfs://{host}{quote(unquote(export))}'
    return volumes


def _parts(url):
    parsed = urlsplit(url)
    return parsed.scheme, (parsed.hostname or '').lower(), [unquote(s) for s in parsed.path.split('/') if s]


def _mounted_path(destination, volumes):
    """Local path for a network URL when one of its parents is a mounted volume."""
    scheme, host, wanted = _parts(destination)
    lowered = [s.lower() for s in wanted]
    best = None
    for point, url in volumes.items():
        volume_scheme, volume_host, have = _parts(url)
        if (volume_scheme, volume_host) != (scheme, host) or len(have) > len(wanted):
            continue
        if [s.lower() for s in have] != lowered[:len(have)]:
            continue
        if best is None or len(have) > len(best[1]):
            best = (point, have)
    if best is None:
        return None
    point, have = best
    return point.joinpath(*wanted[len(have):])


def _resolve_macos(destination):
    parsed = urlsplit(destination)
    if parsed.scheme not in {'smb', 'nfs'}:
        raise RuntimeError('Connect to this location in Finder (Go → Connect to Server…), '
                           'then choose its folder under /Volumes.')
    path = _mounted_path(destination, mounted_volumes())
    if path is None:
        scheme, _, segments = _parts(destination)
        share = segments[:1] if scheme == 'smb' else segments
        url = f'{scheme}://{parsed.netloc}/' + '/'.join(quote(s) for s in share)
        try:
            # Finder mounts the share, asking for credentials when the keychain has none.
            subprocess.run(['open', url], capture_output=True, timeout=30, check=True)
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError('Finder could not connect to the NAS. Open it in Finder '
                               '(Go → Connect to Server…) and sign in, then retry.') from exc
        deadline = time.monotonic() + MOUNT_WAIT
        while path is None and time.monotonic() < deadline:
            time.sleep(MOUNT_POLL)
            path = _mounted_path(destination, mounted_volumes())
        if path is None:
            raise RuntimeError('The NAS did not connect. Finish signing in through Finder, '
                               'then retry the export.')
    return path


def resolve_destination(destination):
    parsed = urlsplit(str(destination))
    if not parsed.scheme:
        return Path(destination).expanduser()
    if parsed.scheme == 'file':
        return Path(unquote(parsed.path))
    if parsed.scheme not in NETWORK_SCHEMES:
        raise ValueError('Choose a local folder or an SMB, SFTP or NFS folder.')
    if PLATFORM == 'darwin':
        return _resolve_macos(str(destination))
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
        # Volumes already mounted in Finder count as network places, so a folder
        # chosen under /Volumes is remembered by its network URL and re-mounted later.
        self.mounts = dict(mounted_volumes()) if PLATFORM == 'darwin' else {}
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
        if PLATFORM == 'darwin':
            if self.mounts:
                self.setSidebarUrls(self.sidebarUrls()
                                    + [QUrl.fromLocalFile(str(path)) for path in self.mounts])
            else:
                self.notice.setText('To export to the NAS, connect to it in Finder first. '
                                    'It then appears here under /Volumes.')
        if urlsplit(destination).scheme in NETWORK_SCHEMES:
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
