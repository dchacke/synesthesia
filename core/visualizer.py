"""Feed the visualizer, a WebGL page in the browser, from a small local web
server: it serves the page and streams messages to it as server-sent
events. It listens on 127.0.0.1 only, and every request needs the random
token in the page's URL, so other sites can't read what it streams."""

import json
import queue
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

KEEPALIVE = 15  # seconds between pings, so idle connections stay open


class Visualizer:
    """Serves `page` and broadcasts messages to every open copy of it. The
    latest 'state' message is replayed to pages that connect later."""

    def __init__(self, page, port=0, token=None):
        self.page = page
        self.token = token or secrets.token_urlsafe(16)
        self.state = None
        self._clients = set()
        self._lock = threading.Lock()
        self.server = ThreadingHTTPServer(('127.0.0.1', port), self._handler())
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       name='Synesthesia visualizer', daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:{}/?token={}'.format(self.server.server_address[1], self.token)

    def publish(self, message):
        if message.get('type') == 'state':
            self.state = message
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.put(message)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            client.put(None)  # ends the stream

    def _handler(self):
        visualizer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                url = urlparse(self.path)
                if parse_qs(url.query).get('token') != [visualizer.token]:
                    self.send_error(403)
                elif url.path == '/':
                    self._send_page()
                elif url.path == '/events':
                    self._stream()
                else:
                    self.send_error(404)

            def _send_page(self):
                body = visualizer.page.replace('{{TOKEN}}', visualizer.token).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _stream(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                messages = queue.Queue()
                if visualizer.state is not None:
                    messages.put(visualizer.state)
                with visualizer._lock:
                    visualizer._clients.add(messages)
                try:
                    while True:
                        try:
                            message = messages.get(timeout=KEEPALIVE)
                        except queue.Empty:
                            self.wfile.write(b': ping\n\n')
                        else:
                            if message is None:
                                return
                            event = 'data: ' + json.dumps(message) + '\n\n'
                            self.wfile.write(event.encode('utf-8'))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    with visualizer._lock:
                        visualizer._clients.discard(messages)

            def log_message(self, *args):
                pass  # keep Sublime's console quiet

        return Handler
