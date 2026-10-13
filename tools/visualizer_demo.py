"""Run the visualizer without Sublime, on a made-up project whose health
swings from beautiful to cursed and back, with an edit every few seconds.

Usage: python3 tools/visualizer_demo.py [port] [token]
"""

import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.visualizer import Visualizer  # noqa: E402

FILES = ['app/models/user.rb', 'app/models/post.rb', 'app/controllers/posts_controller.rb',
         'app/helpers/posts_helper.rb', 'app/views/posts/index.rb', 'lib/markdown.rb',
         'lib/search.rb', 'config/routes.rb', 'test/models/user_test.rb', 'test/system/posts_test.rb']


def main(port=8765, token='demo'):
    with open(os.path.join(ROOT, 'visualizer', 'index.html'), encoding='utf-8') as f:
        visualizer = Visualizer(f.read(), port=int(port), token=token)
    print(visualizer.url, flush=True)
    rng = random.Random(1)
    lines = {name: rng.randint(20, 400) for name in FILES}
    started = time.time()
    while True:
        elapsed = time.time() - started
        health = 0.55 + 0.45 * math.cos(elapsed / 20)  # a minute and a bit from top to bottom
        files = [{'name': name, 'label': name, 'lines': lines[name],
                  'health': max(0.0, min(1.0, health + rng.uniform(-0.2, 0.2))),
                  'broken': health < 0.3 and rng.random() < 0.3} for name in FILES]
        visualizer.publish({'type': 'state', 'health': health, 'files': files})
        if rng.random() < 0.6:
            name = rng.choice(FILES)
            visualizer.publish({'type': 'change', 'file': name, 'label': name,
                                'way': rng.choice(['up', 'down', 'same'])})
        time.sleep(2.5)


if __name__ == '__main__':
    main(*sys.argv[1:])
