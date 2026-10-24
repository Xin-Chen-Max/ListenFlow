"""Run the local desktop server and open its page after it becomes ready."""
import argparse
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.chdir(BASE)


def open_when_ready(url: str) -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-pause', action='store_true', help='Used by the Windows launcher for automated checks.')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    import access
    if access.get_mode() != 'local':
        print('Private mode is configured. Use its dedicated launcher instead of the desktop launcher.')
        return 1
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            print(f'Port {args.port} is already in use. Stop that server before starting another instance.')
            return 1
    url = f'http://127.0.0.1:{args.port}'
    print('ListenFlow: ' + url, flush=True)
    print('Keep this window open. Press Ctrl+C to stop the server.', flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    import uvicorn
    uvicorn.run('app:app', host='127.0.0.1', port=args.port, workers=1, proxy_headers=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
