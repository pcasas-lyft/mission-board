#!/usr/bin/env python3
import json, os, threading, queue, subprocess, getpass
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE  = os.path.join(INSTALL_DIR, 'tasks.json')

# SSE: list of per-client queues
_clients = []
_clients_lock = threading.Lock()

# File I/O lock — prevents concurrent writes from corrupting tasks.json
_file_lock = threading.Lock()


def broadcast(msg):
    with _clients_lock:
        # Snapshot the list so we never mutate it while iterating
        snapshot = list(_clients)
    dead = []
    for q in snapshot:
        try:
            q.put_nowait(msg)
        except Exception:
            dead.append(q)
    if dead:
        with _clients_lock:
            for q in dead:
                if q in _clients:
                    _clients.remove(q)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/tasks':
            data = b'null'
            with _file_lock:
                if os.path.exists(TASKS_FILE):
                    with open(TASKS_FILE, 'rb') as f:
                        data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        elif self.path == '/events':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self._cors()
            self.end_headers()

            q = queue.Queue()
            with _clients_lock:
                _clients.append(q)

            try:
                while True:
                    try:
                        msg = q.get(timeout=25)
                        self.wfile.write(f'data: {msg}\n\n'.encode())
                        self.wfile.flush()
                    except queue.Empty:
                        # keepalive comment so the connection stays open
                        self.wfile.write(b': ping\n\n')
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                with _clients_lock:
                    if q in _clients:
                        _clients.remove(q)

        else:
            super().do_GET()

    def do_PATCH(self):
        # PATCH /tasks/<id>  — merge-update a single task
        if self.path.startswith('/tasks/'):
            task_id = self.path[len('/tasks/'):]
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)

            try:
                patch = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"invalid JSON"}')
                return

            with _file_lock:
                tasks = []
                if os.path.exists(TASKS_FILE):
                    with open(TASKS_FILE, 'r') as f:
                        tasks = json.load(f)

                found = False
                for t in tasks:
                    if t.get('id') == task_id:
                        t.update(patch)
                        found = True
                        break

                if not found:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(b'{"error":"task not found"}')
                    return

                with open(TASKS_FILE, 'w') as f:
                    json.dump(tasks, f)

            broadcast('update')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    def do_POST(self):
        # POST /update — git pull and report what changed
        if self.path == '/update':
            try:
                result = subprocess.run(
                    ['git', '-C', INSTALL_DIR, 'pull'],
                    capture_output=True, text=True, timeout=30
                )
                output = (result.stdout + result.stderr).strip()
                already_current = 'Already up to date' in output
                changed = result.returncode == 0 and not already_current
                # Any .py or .sh file change means the server should restart
                server_changed = changed and any(
                    name in output for name in [
                        'server.py', 'install-hooks.py', 'gen-status.py',
                        'archive-tasks.py', 'notif-summary.py',
                        'auto-claim-task.py', 'auto-unclaim-task.py',
                    ]
                )
                resp = json.dumps({
                    'ok': result.returncode == 0,
                    'output': output,
                    'changed': changed,
                    'server_changed': server_changed,
                })
            except Exception as e:
                resp = json.dumps({'ok': False, 'output': str(e), 'changed': False, 'server_changed': False})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(resp.encode())
            return

        # POST /restart — reload the launchd agent (macOS only)
        if self.path == '/restart':
            username = getpass.getuser()
            plist = os.path.expanduser(f'~/Library/LaunchAgents/com.{username}.todo-tracker.plist')
            if not os.path.exists(plist):
                resp = json.dumps({'ok': False, 'output': 'launchd agent not found — restart the server manually'})
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(resp.encode())
                return

            def _restart():
                import time
                time.sleep(1.2)  # give the HTTP response time to land
                subprocess.run(['launchctl', 'unload', plist], capture_output=True)
                subprocess.run(['launchctl', 'load',   plist], capture_output=True)

            threading.Thread(target=_restart, daemon=True).start()
            resp = json.dumps({'ok': True, 'output': 'Restarting… page will reload shortly.'})
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(resp.encode())
            return

        # POST /tasks/new — append a single new task atomically
        if self.path == '/tasks/new':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)

            try:
                new_task = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"invalid JSON"}')
                return

            if not isinstance(new_task, dict) or not new_task.get('title'):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"task must be an object with a title"}')
                return

            import time
            # Fill in defaults so the UI always gets a well-formed task
            new_task.setdefault('id', str(int(time.time() * 1000)))
            new_task.setdefault('status', 'todo')
            new_task.setdefault('done', False)
            new_task.setdefault('ongoing', False)
            new_task.setdefault('activeNow', False)
            new_task.setdefault('priority', 'none')
            new_task.setdefault('day', 'unscheduled')
            new_task.setdefault('notes', '')
            new_task.setdefault('subtasks', [])
            new_task.setdefault('prLink', '')
            new_task.setdefault('blockedOn', '')
            new_task.setdefault('noteHistory', [])
            new_task.setdefault('createdAt', new_task['id'])
            new_task.setdefault('lastUpdated', new_task['id'])

            with _file_lock:
                tasks = []
                if os.path.exists(TASKS_FILE):
                    with open(TASKS_FILE, 'r') as f:
                        tasks = json.load(f)
                tasks.append(new_task)
                with open(TASKS_FILE, 'w') as f:
                    json.dump(tasks, f)

            broadcast('update')
            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'id': new_task['id']}).encode())
            return

        if self.path == '/tasks':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)

            # Validate JSON before touching the file
            try:
                json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"invalid JSON"}')
                return

            with _file_lock:
                with open(TASKS_FILE, 'wb') as f:
                    f.write(body)
            broadcast('update')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, *args):
        pass  # suppress request logs


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    port = 3456
    server = ThreadedHTTPServer(('', port), Handler)
    print(f'Todo tracker → http://localhost:{port}')
    server.serve_forever()
