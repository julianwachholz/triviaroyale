#!/usr/bin/env python

import asyncio
import json
import logging
import os
import ssl
import websockets

from trivia.game import TriviaGame
from trivia.models import *


logger = logging.getLogger('websockets.server')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


class GameController(object):
    """
    Game controller handling users and game interaction.

    """
    def __init__(self):
        self.clients = set()
        self.players = {}

    def join(self, ws):
        """
        Add the client to the list of connected ones.
        This doesn't start interaction yet, though.

        """
        if ws not in self.clients:
            self.clients.add(ws)

    def leave(self, ws):
        """
        Remove the client from the connected list.
        Also remove the Player object if the client was logged in.

        """
        if ws in self.clients:
            if ws in self.players:
                asyncio.async(broadcast({
                    'system': "{} left.".format(self.players[ws]['name']),
                }))
                del self.players[ws]
            self.clients.remove(ws)

    def _set_name(self, ws, name, old_name=None):
        asyncio.async(send(ws, {'setinfo': {
            'playername': name,
        }}))
        if old_name is None:
            asyncio.async(broadcast({
                'system': "{} joined.".format(name),
            }))
        else:
            asyncio.async(broadcast({
                'system': "{} is now known as <b>{}</b>.".format(old_name, name),
            }))

    def _rename_player(self, ws, new_name):
        player = self.players[ws]

        if player['name'] == new_name:
            asyncio.async(send(ws, {
                'system': 'You are already known as <b>{}</b>.'.format(new_name),
            }))
        else:
            with db_session():
                if exists(p for p in Player if p.name == new_name):
                    asyncio.async(send(ws, {
                        'system': 'This name is not available: <b>{}</b>.'.format(new_name),
                    }))
                else:
                    self._set_name(ws, new_name, old_name=player['name'])
                    Player[player['id']].set(name=new_name)
                    player['name'] = new_name

    @db_session
    def _set_password(self, ws, password):
        player = self.players[ws]
        player = Player[self.players[ws]['id']]
        player.set_password(password)
        asyncio.async(send(ws, {
            'system': 'Password successfully changed!',
        }))

    @db_session
    def login(self, ws, name, password=None):
        if ws in self.players.keys():
            if password is not None:
                return self._set_password(ws, password)
            return self._rename_player(ws, name)

        player = get(p for p in Player if p.name == name)

        if player is None:
            player = Player(name=name)
            commit()
        elif not player.check_password(password):
            if password is None:
                asyncio.async(send(ws, {
                    'prompt': 'password',
                    'data': {'login': name},
                }))
                return
            else:
                asyncio.async(send(ws, {
                    'system': 'Invalid username/password! '
                              '<a href="#" onclick="modal(\'password\', {{login:\'{}\'}})">'
                              'Try again</a>'.format(name),
                }))
                return

        self.players[ws] = {
            'id': player.id,
            'name': player.name,
        }
        self._set_name(ws, player.name)

        if not player.has_password():
            asyncio.async(send(ws, {
                'system': 'You currently have no password, '
                          '<a href="#" onclick="modal(\'password\', {{login:\'{}\'}})">'
                          'click here to set a password!</a>'.format(player.name),
            }))
        asyncio.async(send(ws, {'setinfo': trivia.get_round_info()}))

    def chat(self, ws, text):
        player_name = self.players[ws]['name']
        asyncio.async(broadcast({
            'player': player_name,
            'text': text,
        }))
        asyncio.async(trivia.chat(player_name, text))


game = GameController()


@asyncio.coroutine
def game_handle(ws, data):
    keys = data.keys()

    if 'ping' in keys:
        asyncio.async(send(ws, {'pong': data.get('ping')}))

    if 'login' in keys:
        game.login(ws, data.get('login'), data.get('password', None))

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
    listen_port = int(os.environ.get('LISTEN_PORT', 8765))

    if 'CERT_FILE' in os.environ and 'CERT_KEY' in os.environ:
        secure = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        secure.load_cert_chain(os.environ['CERT_FILE'], os.environ['CERT_KEY'])
    else:
        secure = None

    db.bind('postgres', database='trivia')
    db.generate_mapping()

    server = websockets.serve(handler, listen_ip, listen_port, ssl=secure)
    trivia = TriviaGame(broadcast)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(server)
    loop.run_until_complete(trivia.run())
    loop.run_forever()
