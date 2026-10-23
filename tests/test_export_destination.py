import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from types import SimpleNamespace
import subprocess
import pytest
from PySide6.QtWidgets import QApplication
from gr_studio import export_destination as module


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
    dialog = module.ExportFolderDialog(str(tmp_path))
    folder = tmp_path / 'Photo exports'
    folder.mkdir()
    dialog.mounts[tmp_path] = 'smb://nas/share'
    dialog.selectFile(str(folder))
    assert dialog.destination() == 'smb://nas/share/Photo%20exports'
    assert dialog.shortcuts[0].text() == 'NAS'
    dialog.close()
    app.processEvents()
