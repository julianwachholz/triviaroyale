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
            name = self.players[ws].get('name', None)
            if name is not None:
                asyncio.async(broadcast({
                    'system': "{} left.".format(name),
                }))
            del self.players[ws]

    def setName(self, ws, name, prompt=False):
        oldname = self.players[ws].get('name', None)

        if oldname == name:
            asyncio.async(send(ws, {
                'system': 'You are already known as <b>{}</b>.'.format(name),
            }))
            return

        if not self._checkNameAvailable(name):
            asyncio.async(send(ws, {
                'system': 'The name <b>{}</b> is taken, please '
                          '<a href="#" onclick="modal(\'login\');return false;">choose a different one</a>.'.format(name),
            }))
            return

        if oldname is not None:
            asyncio.async(broadcast({
                'system': "{} is now known as <b>{}</b>.".format(oldname, name),
            }))
        else:
            asyncio.async(broadcast({
                'system': "{} joined.".format(name),
            }))

        self.players[ws]['name'] = name
        asyncio.async(send(ws, {'setinfo': {
            'playername': name,
        }}))

    def _checkNameAvailable(self, name):
        for ws, player in self.players.items():
            if player.get('name', None) == name:
                return False
        return True

game = Game()


@asyncio.coroutine
def game_handle(ws, data):
    keys = data.keys()

    if 'ping' in keys:
        asyncio.async(send(ws, {'pong': data.get('ping')}))

    if 'login' in keys:
        game.setName(ws, data.get('login'))

    if 'text' in keys:
        asyncio.async(broadcast({
            'player': game.players[ws]['name'],
            'text': data.get('text'),
        }))


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


server = websockets.serve(handler, 'localhost', 8765)

loop = asyncio.get_event_loop()
loop.run_until_complete(server)
loop.run_forever()
