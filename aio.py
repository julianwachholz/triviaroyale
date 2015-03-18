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
        self.clients = set()
        self.players = {}

    def join(self, ws):
        if ws not in self.clients:
            self.clients.add(ws)
            self.players[ws] = {}

    def leave(self, ws):
        if ws in self.clients:
            self.clients.remove(ws)
            del self.players[ws]

    def setName(self, ws, name):
        self.players[ws]['name'] = name


game = Game()


@asyncio.coroutine
def game_handle(ws, data):
    keys = data.keys()

    if 'ping' in keys:
        answer = json.dumps({'pong': data.get('ping')})
        yield from ws.send(answer)

    if 'login' in keys:
        login = data.get('login')
        game.setName(ws, login)
        answer = json.dumps({'setinfo': {
            'playername': login,
        }})
        yield from ws.send(answer)

    if 'text' in keys:
        message = json.dumps({
            'player': game.players[ws]['name'],
            'text': data.get('text'),
        })
        asyncio.async(broadcast(message))


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


@asyncio.coroutine
def broadcast(message):
    for ws in game.players:
        if ws.open:
            yield from ws.send(message)


server = websockets.serve(handler, 'localhost', 8765)

loop = asyncio.get_event_loop()
loop.run_until_complete(server)
loop.run_forever()
