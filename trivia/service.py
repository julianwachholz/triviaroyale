# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import gevent

from trivia.game import TriviaGame


logger = logging.getLogger(__name__)


class TriviaChat(object):
    """
    Pub/sub system.

    """
    PUBSUB_CHANNEL = 'trivia'
    DISCONNECT_HANDLE = '__DISCONNECT__'

    def __init__(self, app, redis):
        self.game = TriviaGame()
        self.clients = []
        self.pubsub = redis.pubsub()
        self.pubsub.subscribe(self.PUBSUB_CHANNEL)

    @classmethod
    def publish(cls, redis, message):
        """
        Publish an event.

        """
        redis.publish(cls.PUBSUB_CHANNEL, message)

    def register(self, client):
        """
        Register a connection for updates.

        """
        self.clients.append(client)

    def _iter_data(self):
        for message in self.pubsub.listen():
            data = message.get('data')

            self.game.handle(data)

            if message['type'] == 'message':
                logger.info('SEND {}'.format(data))
                yield data

    def send(self, client, data):
        """
        Send data to a client.

        """
        try:
            client.send(data)
        except Exception:
            self.clients.remove(client)

    def start(self):
        self.game.start()
        gevent.spawn(self.run)

    def run(self):
        """
        Listen for messages in redis and distribute them.

        """
        for data in self._iter_data():
            for client in self.clients:
                gevent.spawn(self.send, client, data)
