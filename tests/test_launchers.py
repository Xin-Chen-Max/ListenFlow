"""Exercise startup boundaries and HTTP readiness without inference or a browser."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
START = ROOT / 'scripts/start.py'


def environment(tmp_path):
    env = os.environ.copy()
    env.update(LISTENFLOW_MODE='local', LISTENFLOW_DATA_DIR=str(tmp_path),
               LIBRARY_DB=str(tmp_path / 'library.db'), PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1')
    env.pop('LISTENFLOW_PRIVATE_USER', None)
    env.pop('LISTENFLOW_PRIVATE_ORIGIN', None)
    return env


def test_private_mode_cannot_be_bypassed_by_desktop_launcher(tmp_path):
    env = environment(tmp_path)
    env['LISTENFLOW_MODE'] = 'private'
    result = subprocess.run([sys.executable, str(START), '--no-browser'], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'Private mode is configured' in result.stdout


def test_occupied_port_is_not_treated_as_new_server(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run([sys.executable, str(START), '--no-browser', '--port', str(port)],
                                env=environment(tmp_path), capture_output=True, text=True)
    assert result.returncode == 1
    assert 'already in use' in result.stdout


def test_launcher_starts_isolated_http_service(tmp_path):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    with (tmp_path / 'server.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, str(START), '--no-browser', '--port', str(port)],
                                  env=environment(tmp_path), stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(150):
                assert server.poll() is None, (tmp_path / 'server.log').read_text(encoding='utf-8')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=1) as response:
                        assert response.status == 200
                        assert b'ListenFlow' in response.read()
                        return
                except (OSError, urllib.error.URLError):
                    time.sleep(.1)
            raise AssertionError('Desktop server did not become ready.')
        finally:
            if server.poll() is None:
                server.terminate()
            server.wait(timeout=10)
