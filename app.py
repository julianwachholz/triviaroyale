#!/usr/bin/env python

import asyncio
import json
import logging
import os
import ssl
import websockets

from trivia.chat import GameController
from trivia.game import TriviaGame
from trivia.models import db


logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)

game = GameController()


@asyncio.coroutine
def game_handle(ws, data):
    keys = data.keys()

    if 'ping' in keys and ws.open:
        asyncio.async(send(ws, {'pong': data.get('ping')}))

    if 'command' in keys:
        game.command(ws, data.get('command'), data)

    if 'login' in keys:
        game.login(ws, data.get('login'), data.get('password', None), data.get('auto', False))

    if 'text' in keys:
        game.chat(ws, data.get('text'))


@asyncio.coroutine
def handler(ws, path):
    game.join(ws)
    while True:
        message = yield from ws.recv()
        if message is None:
            game.leave(ws)
            break
        data = json.loads(message)
        asyncio.async(game_handle(ws, data))

        if 'ping' not in data:
            yield from asyncio.sleep(0.25)  # message throttling


@asyncio.coroutine
def send(ws, message):
    message = json.dumps(message)
    if ws.open:
        yield from ws.send(message)


@asyncio.coroutine
def broadcast(message):
    message = json.dumps(message)
    for ws in game.clients:
        if ws.open:
            yield from ws.send(message)


if __name__ == '__main__':
    listen_ip = os.environ.get('LISTEN_IP', 'localhost')
    listen_port = int(os.environ.get('LISTEN_PORT', 8080))

    if 'CERT_FILE' in os.environ and 'CERT_KEY' in os.environ:
        secure = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        secure.load_cert_chain(os.environ['CERT_FILE'], os.environ['CERT_KEY'])
    else:
        secure = None

    db.bind('postgres', database='trivia')
    db.generate_mapping(create_tables=True)

    server = websockets.serve(handler, listen_ip, listen_port, ssl=secure)

    trivia = TriviaGame(broadcast)
    game.trivia = trivia
    game.send = send
    game.broadcast = broadcast

    loop = asyncio.get_event_loop()
    loop.run_until_complete(server)
    loop.run_until_complete(trivia.run())
    loop.run_forever()
