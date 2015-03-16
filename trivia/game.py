# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import gevent

from .models import db


logger = logging.getLogger(__name__)


class TriviaGame(object):
    """
    The main trivia game.

    """
    def handle(self, data):
        logger.info('handling data: {}'.format(data))

    def start(self):
        gevent.spawn(self.run)

    def run(self):
        db.bind('postgres', host='localhost', database='trivia')
        db.generate_mapping(create_tables=True)

        while True:
            gevent.sleep(0.1)
