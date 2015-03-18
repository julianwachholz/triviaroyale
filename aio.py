#!/usr/bin/env python

import asyncio
import json
import logging
import websockets


logger = logging.getLogger('websockets.server')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


class Game(object):
    STATE_IDLE = 'idle'

    def __init__(self):
        self.state = self.STATE_IDLE
        self.players = set()

    def join(self, ws):
        self.players.add(ws)

    def leave(self, ws):
        self.players.remove(ws)


game = Game()

@asyncio.coroutine
def game_handle(ws, message):
    data = json.loads(message)
    if data.get('ping'):
        answer = json.dumps({'pong': data.get('ping')})
        print(answer)
        yield from ws.send(answer)


@asyncio.coroutine
def handler(ws, path):
    game.join(ws)
    while True:
        message = yield from ws.recv()
        if message is None:
            game.leave(ws)
            break

        data = json.loads(message)

        if data.get('text'):
            asyncio.async(broadcast(data.get('text')))
        asyncio.async(game_handle(ws, message))


@asyncio.coroutine
def broadcast(text):
    message = json.dumps({'text': text})
    for ws in game.players:
        if ws.open:
            yield from ws.send(message)


server = websockets.serve(handler, 'localhost', 8765)

loop = asyncio.get_event_loop()
loop.run_until_complete(server)
loop.run_forever()
