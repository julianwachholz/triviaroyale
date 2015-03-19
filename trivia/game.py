import asyncio
import logging

from .models import *


logger = logging.getLogger(__name__)


class TriviaGame(object):
    """
    The main trivia game.

    """
    def __init__(self, broadcast):
        self.broadcast = broadcast

    @asyncio.coroutine
    def run(self):
        i = 0
        while True:
            i += 1
            asyncio.async(self.broadcast({
                'system': "Trivia is running: #{}".format(i),
            }))
            yield from asyncio.sleep(5.0)
