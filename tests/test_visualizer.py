import http.client
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.visualizer import Visualizer  # noqa: E402


class VisualizerTest(unittest.TestCase):
    def setUp(self):
        self.visualizer = Visualizer('<p>{{TOKEN}}</p>', pages={'/tiles': '<i>{{TOKEN}}</i>'})
        self.addCleanup(self.visualizer.stop)
        self.port = self.visualizer.server.server_address[1]
        self.token = self.visualizer.token

    def get(self, path):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        self.addCleanup(connection.close)
        connection.request('GET', path)
        return connection.getresponse()

    def test_the_page_needs_the_token(self):
        self.assertEqual(self.get('/').status, 403)
        self.assertEqual(self.get('/?token=wrong').status, 403)
        page = self.get('/?token=' + self.token)
        self.assertEqual(page.read().decode(), '<p>{}</p>'.format(self.token))
        self.assertTrue(self.visualizer.url.endswith('/?token=' + self.token))

    def test_other_pages_sit_beside_it(self):
        self.assertEqual(self.get('/tiles').status, 403)
        page = self.get('/tiles?token=' + self.token)
        self.assertEqual(page.read().decode(), '<i>{}</i>'.format(self.token))
        self.assertTrue(self.visualizer.url_for('/tiles').endswith('/tiles?token=' + self.token))
        self.assertEqual(self.get('/nope?token=' + self.token).status, 404)

    def test_events_replay_the_state_then_stream(self):
        self.visualizer.publish({'type': 'state', 'health': 0.5})
        events = self.get('/events?token=' + self.token)
        self.assertEqual(events.getheader('Content-Type'), 'text/event-stream')

        def next_event():
            line = events.fp.readline()
            events.fp.readline()  # the blank line after each event
            return json.loads(line.decode()[len('data: '):])
        self.assertEqual(next_event(), {'type': 'state', 'health': 0.5})
        self.visualizer.publish({'type': 'change', 'file': 'a.py', 'way': 'up'})
        self.assertEqual(next_event()['file'], 'a.py')


if __name__ == '__main__':
    unittest.main()
