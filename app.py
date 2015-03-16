# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import logging

import gevent
from flask import Flask, render_template
from flask_sockets import Sockets
from redis.client import Redis

from trivia.service import TriviaChat


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost/0')

app = Flask(__name__)
socket = Sockets(app)
redis = Redis.from_url(REDIS_URL)


chat = TriviaChat(app, redis)
chat.start()


@app.route('/')
def index():
    return render_template('index.html')


@socket.route('/ws')
def websocket(ws):
    chat.register(ws)

    while not ws.closed:
        gevent.sleep(0.1)
        message = ws.receive()

        if message:
            logger.info('RECV {}'.format(message))
            TriviaChat.publish(redis, message)
