#!/usr/bin/env python3
import json, os, re, threading, queue, subprocess, getpass, uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

INSTALL_DIR       = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE        = os.path.join(INSTALL_DIR, 'tasks.json')
JIRA_CONFIG_FILE  = os.path.join(INSTALL_DIR, 'jira-config.json')
JIRA_DEFAULT_URL  = ''

# SSE: list of per-client queues
_clients = []
_clients_lock = threading.Lock()

# File I/O lock — prevents concurrent writes from corrupting tasks.json
_file_lock = threading.Lock()

# Regen WORKSTATUS.md + DONELOG.md in the background after any write
def _regen_docs():
    try:
        subprocess.run(['python3', os.path.join(INSTALL_DIR, 'gen-status.py')],
                       capture_output=True, timeout=15)
        subprocess.run(['python3', os.path.join(INSTALL_DIR, 'gen-donelog.py')],
                       capture_output=True, timeout=15)
    except Exception:
        pass

def regen_docs_async():
    threading.Thread(target=_regen_docs, daemon=True).start()


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

        elif self.path == '/jira-config':
            # Return whether Jira is configured (never return the token itself)
            cfg = {}
            if os.path.exists(JIRA_CONFIG_FILE):
                try:
                    with open(JIRA_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            resp = json.dumps({
                'configured': bool(cfg.get('token')),
                'baseUrl': cfg.get('baseUrl', JIRA_DEFAULT_URL),
            })
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(resp.encode())

        elif self.path.startswith('/jira/'):
            key = self.path[len('/jira/'):].upper()
            if not re.match(r'^[A-Z]+-\d+$', key):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors(); self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid Jira key format'}).encode())
                return
            # Load config
            cfg = {}
            if os.path.exists(JIRA_CONFIG_FILE):
                try:
                    with open(JIRA_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            token = cfg.get('token', '')
            base_url = cfg.get('baseUrl', JIRA_DEFAULT_URL).rstrip('/')

            if not token:
                self.send_response(401)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Jira not configured — add your PAT in Jira settings'}).encode())
                return

            import urllib.request, urllib.error
            try:
                req = urllib.request.Request(
                    f'{base_url}/rest/api/2/issue/{key}',
                    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                )
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read())
                fields = data.get('fields', {})
                status = fields.get('status', {})
                assignee = fields.get('assignee') or {}
                resp = json.dumps({
                    'key': data['key'],
                    'summary': fields.get('summary', ''),
                    'status': status.get('name', ''),
                    'statusCategory': status.get('statusCategory', {}).get('colorName', ''),
                    'assignee': assignee.get('displayName', ''),
                    'priority': (fields.get('priority') or {}).get('name', ''),
                    'type': (fields.get('issuetype') or {}).get('name', ''),
                    'url': f'{base_url}/browse/{data["key"]}',
                })
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(resp.encode())
            except urllib.error.HTTPError as e:
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                msg = 'Not found' if e.code == 404 else f'Jira error {e.code}'
                self.wfile.write(json.dumps({'error': msg}).encode())
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())

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
        # PATCH /tasks/<id>/log — append a log entry atomically
        if self.path.startswith('/tasks/') and self.path.endswith('/log'):
            task_id = self.path[len('/tasks/'):-len('/log')]
            if not re.match(r'^[a-zA-Z0-9_-]+$', task_id):
                self.send_response(400); self._cors(); self.end_headers()
                self.wfile.write(b'{"error":"invalid task id"}'); return
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400); self._cors(); self.end_headers()
                self.wfile.write(b'{"error":"invalid JSON"}'); return

            text = (payload.get('text') or '').strip()
            if not text:
                self.send_response(400); self._cors(); self.end_headers()
                self.wfile.write(b'{"error":"text is required"}'); return

            from datetime import datetime, timezone
            entry = {
                'date': payload.get('date') or datetime.now(timezone.utc).isoformat(),
                'text': text,
            }

            with _file_lock:
                tasks = []
                if os.path.exists(TASKS_FILE):
                    with open(TASKS_FILE) as f:
                        tasks = json.load(f)
                found = False
                for t in tasks:
                    if t.get('id') == task_id:
                        t.setdefault('log', [])
                        t['log'].append(entry)
                        t['lastUpdated'] = entry['date']
                        found = True
                        break
                if not found:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self._cors(); self.end_headers()
                    self.wfile.write(b'{"error":"task not found"}'); return
                with open(TASKS_FILE, 'w') as f:
                    json.dump(tasks, f)

            broadcast('update')
            regen_docs_async()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors(); self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'entry': entry}).encode())
            return

        # PATCH /tasks/<id>  — merge-update a single task
        if self.path.startswith('/tasks/'):
            task_id = self.path[len('/tasks/'):]
            if not re.match(r'^[a-zA-Z0-9_-]+$', task_id):
                self.send_response(400); self._cors(); self.end_headers()
                self.wfile.write(b'{"error":"invalid task id"}'); return
            length = int(self.headers.get('Content-Length') or 0)
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
            regen_docs_async()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    def do_POST(self):
        # POST /jira-config — save Jira token + base URL
        if self.path == '/jira-config':
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self._cors()
                self.end_headers()
                self.wfile.write(b'{"error":"invalid JSON"}')
                return
            # Load existing config and merge so we don't lose the token on a baseUrl-only update
            cfg = {}
            if os.path.exists(JIRA_CONFIG_FILE):
                try:
                    with open(JIRA_CONFIG_FILE) as f:
                        cfg = json.load(f)
                except Exception:
                    pass
            if 'token' in payload and payload['token']:
                cfg['token'] = payload['token']
            if 'baseUrl' in payload:
                cfg['baseUrl'] = payload['baseUrl'].rstrip('/')
            with open(JIRA_CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=2)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return

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
            length = int(self.headers.get('Content-Length') or 0)
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

            # Fill in defaults so the UI always gets a well-formed task
            new_task.setdefault('id', uuid.uuid4().hex[:12])
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
            new_task.setdefault('jiraKey', '')
            new_task.setdefault('log', [])
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
            regen_docs_async()
            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({'ok': True, 'id': new_task['id']}).encode())
            return

        if self.path == '/tasks':
            length = int(self.headers.get('Content-Length') or 0)
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
            regen_docs_async()
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
    server = ThreadedHTTPServer(('127.0.0.1', port), Handler)
    print(f'Todo tracker → http://localhost:{port}')
    server.serve_forever()
