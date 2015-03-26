import asyncio
import time

from trivia.models import *


class GameController(object):
    """
    Controller handles users and interaction with them.

    Login/passwords and chat interaction goes through this.

    """
    CHAT_SCROLLBACK = 20

    def __init__(self):
        self.clients = set()
        self.players = {}
        self.chat_scrollback = []

        self.trivia = None
        self.send = None
        self.broadcast = None

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
                name = self.players[ws]['name']
                del self.players[ws]
                self.trivia.player_count -= 1
                asyncio.async(self.broadcast({
                    'system': "{} left.".format(name),
                    'setinfo': self._get_player_info(),
                }))
            self.clients.remove(ws)

    def _set_name(self, ws, name, old_name=None):
        asyncio.async(self.send(ws, {'setinfo': {
            'playername': name,
        }}))
        if old_name is None:
            self.trivia.player_count += 1
            asyncio.async(self.broadcast({
                'system': "{} joined.".format(name),
                'setinfo': self._get_player_info(),
            }))
        else:
            asyncio.async(self.broadcast({
                'system': "{} is now known as <b>{}</b>.".format(old_name, name),
                'setinfo': self._get_player_info(),
            }))

    def _rename_player(self, ws, new_name):
        player = self.players[ws]

        if player['name'] == new_name:
            asyncio.async(self.send(ws, {
                'system': 'You are already known as <b>{}</b>.'.format(new_name),
            }))
        else:
            with db_session():
                if exists(p for p in Player if p.name == new_name):
                    asyncio.async(self.send(ws, {
                        'system': 'This name is not available: <b>{}</b>.'.format(new_name),
                    }))
                else:
                    old_name = player['name']
                    player['name'] = new_name
                    Player[player['id']].set(name=new_name)
                    self._set_name(ws, new_name, old_name=old_name)

    def _get_player_info(self):
        names = map(lambda player: player['name'], self.players.values())
        return {
            'playercount': len(self.players),
            'playerlist': '<li>{}</li>'.format('</li><li>'.join(names))
        }

    @db_session
    def _set_password(self, ws, password):
        player = self.players[ws]
        player = Player[self.players[ws]['id']]
        player.set_password(password)
        asyncio.async(self.send(ws, {
            'system': 'Password successfully changed!',
        }))

    def command(self, ws, command, args):
        if hasattr(self, command):
            getattr(self, command)(ws, args)

    def vote(self, ws, args):
        value = args.get('vote', 0)
        if value in (-1, 1):
            try:
                player_name = self.players[ws]['name']
            except KeyError:
                return
            if self.trivia.queue_vote(player_name, value):
                asyncio.async(self.send(ws, {'setinfo': {
                    'question-vote':  '<p class="question-vote">Thank you!</p>',
                }}))

    @db_session
    def login(self, ws, name, password=None, auto=False):
        if len(name) > Player.NAME_MAX_LEN:
            return

        if ws in self.players.keys():
            if password is not None:
                return self._set_password(ws, password)
            return self._rename_player(ws, name)

        player = get(p for p in Player if p.name == name)

        if player is None:
            player = Player(name=name)
            commit()
        elif not player.check_password(password):
            if password is None or auto:
                asyncio.async(self.send(ws, {
                    'prompt': 'password',
                    'data': {'login': name},
                }))
                return
            else:
                asyncio.async(self.send(ws, {
                    'system': 'Invalid username/password! '
                              '<a href="#" onclick="modal(\'password\', {{login:\'{}\'}})">'
                              'Try again</a>'.format(name),
                }))
                return

        player.logged_in()

        self.players[ws] = {
            'id': player.id,
            'name': player.name,
            'permissions': player.permissions,
        }
        self._set_name(ws, player.name)

        if not player.has_password():
            asyncio.async(self.send(ws, {
                'system': 'You currently have no password, '
                          '<a href="#" onclick="modal(\'password\', {{login:\'{}\'}})">'
                          'click here to set a password!</a>'.format(player.name),
            }))
        asyncio.async(self.send(ws, {'setinfo': self.trivia.get_round_info()}))
        asyncio.async(self.send(ws, self.chat_scrollback))

    def chat(self, ws, text):
        player = self.players[ws]
        entry = {
            'player': player['name'],
            'text': text,
        }
        asyncio.async(self.broadcast(entry))
        entry.update(time=int(time.time()))

        self.chat_scrollback.append(entry)
        if len(self.chat_scrollback) > self.CHAT_SCROLLBACK:
            self.chat_scrollback = self.chat_scrollback[1:]

        asyncio.async(self.trivia.chat(player, text))
