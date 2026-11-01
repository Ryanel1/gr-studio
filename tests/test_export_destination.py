import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest
from PySide6.QtWidgets import QApplication
from gr_studio import export_destination as module


MAC_MOUNTS = '''/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)
devfs on /dev (devfs, local, nobrowse)
//ryan@192.168.1.239/downloads on /Volumes/downloads (smbfs, nodev, nosuid, mounted by ryan)
//ryan@nas._smb._tcp.local/Photo%20Archive on /Volumes/Photo Archive (smbfs, nodev, nosuid, mounted by ryan)
192.168.1.239:/volume1/music on /Volumes/music (nfs, nodev, nosuid, mounted by ryan)
'''


def test_bookmarks(tmp_path):
    path = tmp_path / 'places'
    path.write_text('<xbel><bookmark href="smb://nas/"><title>NAS</title></bookmark><bookmark href="file:///tmp"><title>Local</title></bookmark></xbel>')
    assert module.network_places(path) == [('NAS', 'smb://nas/')]
    path.write_text('broken')
    assert module.network_places(path) == []


def test_local(tmp_path):
    assert module.resolve_destination(str(tmp_path)) == tmp_path
    assert module.resolve_destination(tmp_path.as_uri()) == tmp_path


def test_mount_and_error(monkeypatch, tmp_path):
    monkeypatch.setattr(module, 'PLATFORM', 'linux')
    monkeypatch.setattr(module.shutil, 'which', lambda _: '/usr/bin/qdbus6')
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=str(tmp_path) + '\n')
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.resolve_destination('smb://nas/photos') == tmp_path
    assert calls[0][-1] == 'smb://nas/photos'
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired('qdbus6', 60)
    monkeypatch.setattr(module.subprocess, 'run', fail)
    with pytest.raises(RuntimeError, match='Could not connect'):
        module.resolve_destination('smb://nas/photos')


def test_dialog_remembers_remote_not_temporary_mount(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, 'network_places', lambda: [('NAS', 'smb://nas/')])
    monkeypatch.setattr(module, 'mounted_volumes', lambda: {})
    dialog = module.ExportFolderDialog(str(tmp_path))
    folder = tmp_path / 'Photo exports'
    folder.mkdir()
    dialog.mounts[tmp_path] = 'smb://nas/share'
    dialog.selectFile(str(folder))
    assert dialog.destination() == 'smb://nas/share/Photo%20exports'
    assert dialog.shortcuts[0].text() == 'NAS'
    dialog.close()
    app.processEvents()


def test_macos_mounted_volumes_parsing():
    assert module.mounted_volumes(MAC_MOUNTS) == {
        Path('/Volumes/downloads'): 'smb://ryan@192.168.1.239/downloads',
        Path('/Volumes/Photo Archive'): 'smb://ryan@nas._smb._tcp.local/Photo%20Archive',
        Path('/Volumes/music'): 'nfs://192.168.1.239/volume1/music',
    }


def test_macos_mounted_path_matches_host_and_share_case_insensitively():
    volumes = module.mounted_volumes(MAC_MOUNTS)
    assert module._mounted_path('smb://192.168.1.239/Downloads/Photo%20exports', volumes) == Path('/Volumes/downloads/Photo exports')
    assert module._mounted_path('smb://ryan@192.168.1.239/downloads', volumes) == Path('/Volumes/downloads')
    assert module._mounted_path('smb://nas._smb._tcp.local/Photo%20Archive/2026', volumes) == Path('/Volumes/Photo Archive/2026')
    assert module._mounted_path('nfs://192.168.1.239/volume1/music/exports', volumes) == Path('/Volumes/music/exports')
    assert module._mounted_path('smb://192.168.1.239/other', volumes) is None
    assert module._mounted_path('smb://elsewhere/downloads', volumes) is None


def test_macos_resolve_uses_mount_or_asks_finder(monkeypatch):
    monkeypatch.setattr(module, 'PLATFORM', 'darwin')
    monkeypatch.setattr(module, 'MOUNT_POLL', 0)
    state = {'mounted': False}
    volumes = module.mounted_volumes(MAC_MOUNTS)
    monkeypatch.setattr(module, 'mounted_volumes', lambda: volumes if state['mounted'] else {})
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        state['mounted'] = True
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.resolve_destination('smb://192.168.1.239/downloads/Photo%20exports') == Path('/Volumes/downloads/Photo exports')
    assert calls == [['open', 'smb://192.168.1.239/downloads']]
    # Already mounted: Finder is not asked again.
    assert module.resolve_destination('smb://192.168.1.239/downloads') == Path('/Volumes/downloads')
    assert len(calls) == 1
    # Finder never finishes mounting.
    state['mounted'] = False
    monkeypatch.setattr(module, 'MOUNT_WAIT', 0)
    def open_only(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='')
    monkeypatch.setattr(module.subprocess, 'run', open_only)
    with pytest.raises(RuntimeError, match='did not connect'):
        module.resolve_destination('smb://192.168.1.239/downloads')
    with pytest.raises(RuntimeError, match='Finder'):
        module.resolve_destination('sftp://192.168.1.239/volume1')


def test_macos_dialog_remembers_volume_as_network_url(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module, 'PLATFORM', 'darwin')
    monkeypatch.setattr(module, 'network_places', lambda: [])
    monkeypatch.setattr(module, 'mounted_volumes', lambda: {tmp_path: 'smb://ryan@nas/downloads'})
    dialog = module.ExportFolderDialog(str(tmp_path))
    folder = tmp_path / 'Photo exports'
    folder.mkdir()
    dialog.selectFile(str(folder))
    assert dialog.destination() == 'smb://ryan@nas/downloads/Photo%20exports'
    assert dialog.shortcuts == []
    assert dialog.notice.text() == ''
    dialog.close()
    app.processEvents()
