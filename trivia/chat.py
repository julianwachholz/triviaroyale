import asyncio
import time
import logging

from trivia.models import Player, db_session, commit


logger = logging.getLogger(__name__)


class GameController(object):
    """
    Controller handles users and interaction with them.

    Login/passwords and chat interaction goes through this.

    """
    CHAT_SCROLLBACK = 30

    COMMANDS = ['login', 'vote', 'start', 'hint']

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
                player = self.players[ws]
                del self.players[ws]
                self.trivia.player_count -= 1
                asyncio.async(self.broadcast({
                    'system': "{} left.".format(player['name']),
                    'setinfo': self._get_player_info(),
                }))
                logger.info('Leave: {} (#{})'.format(player['name'], player['id']))
            self.clients.remove(ws)

    def _set_name(self, ws, player_id, name, old_name=None):
        asyncio.async(self.send(ws, {'setinfo': {
            'playername': name,
        }}))
        if old_name is None:
            self.trivia.player_count += 1
            asyncio.async(self.broadcast({
                'system': "{} joined.".format(name),
                'setinfo': self._get_player_info(),
            }))
            logger.info('Join: {} (#{})'.format(name, player_id))
        else:
            asyncio.async(self.broadcast({
                'system': "{} is now known as *{}*.".format(old_name, name),
                'setinfo': self._get_player_info(),
            }))
            logger.info('Rename: {} to {} (#{})'.format(name, old_name, player_id))

    def _rename_player(self, ws, new_name):
        player = self.players[ws]

        if player['name'] == new_name:
            asyncio.async(self.send(ws, {
                'system': 'You are already known as *{}*.'.format(new_name),
            }))
        else:
            with db_session():
                if Player.exists(lambda p: p.name == new_name):
                    asyncio.async(self.send(ws, {
                        'system': 'This name is not available: *{}*.'.format(new_name),
                    }))
                else:
                    old_name = player['name']
                    player['name'] = new_name
                    Player[player['id']].set(name=new_name)
                    self._set_name(ws, player['id'], new_name, old_name=old_name)

    def _get_player_info(self):
        players = sorted(self.players.values(), key=lambda p: p['joined'])
        count = len(self.players)
        return {
            'playercount': '{} Player{}'.format(count, 's' if count != 1 else ''),
            'players': list(map(lambda player: player['name'], players)),
        }

    @db_session
    def _set_password(self, ws, password):
        player = self.players[ws]
        player = Player[self.players[ws]['id']]
        player.set_password(password)
        asyncio.async(self.send(ws, {
            'system': 'Password successfully changed!',
        }))
        logger.info('Password: {} set new password.'.format(player))

    def command(self, ws, command, args):
        if command in self.COMMANDS and hasattr(self, command):
            fun = getattr(self, command)
            if args is None:
                fun(ws)
            elif isinstance(args, dict):
                fun(ws, **args)
            elif isinstance(args, list):
                fun(ws, *args)
            else:
                fun(ws, args)
        else:
            logger.warn('Unknown command from {}: {} with {}'.format(self.players[ws]['name'], command, args))

    def vote(self, ws, player_vote, *args, **kwargs):
        if player_vote in (-1, 1):
            try:
                player_name = self.players[ws]['name']
            except KeyError:
                return
            if self.trivia.queue_vote(player_name, player_vote):
                asyncio.async(self.send(ws, {'setinfo': {
                    'question-vote': '<p class="question-vote">Thank you!</p>',
                }}))

    def start(self, ws, *args, **kwargs):
        """
        Start a new round if there is no round running yet.

        """
        logger.info('Start: {}'.format(self.players[ws]['name']))
        self.trivia.timeout = asyncio.async(self.trivia.delay_new_round(True))

    def hint(self, ws, *args, **kwargs):
        """
        Request a new hint if currently possible.

        """
        self.trivia.get_hint(from_player=self.players[ws]['name'])

    @db_session
    def login(self, ws, login, password=None, auto=False, *args, **kwargs):
        if len(login) > Player.NAME_MAX_LEN:
            return

        if ws in self.players.keys():
            if password is not None:
                return self._set_password(ws, password)
            return self._rename_player(ws, login)

        player = Player.get(lambda p: p.name == login)

        if player is None:
            player = Player(name=login)
            commit()
        elif not player.check_password(password):
            if password is None or auto:
                asyncio.async(self.send(ws, {
                    'prompt': 'password',
                    'data': {'login': login, 'auto': True},
                }))
                return
            else:
                asyncio.async(self.send(ws, {
                    'system': 'Invalid username/password!',
                    'system_extra': '<a href="#" onclick="showModal(\'password\', {{login:\'{}\'}})">'
                                    'Try again</a>'.format(login),
                }))
                return

        player.logged_in()

        self.players[ws] = {
            'joined': time.time(),
            'id': player.id,
            'name': player.name,
            'permissions': player.permissions,
        }
        self._set_name(ws, player.id, player.name)

        if not player.has_password():
            asyncio.async(self.send(ws, {
                'system': 'You currently have no password!',
                'system_extra': '<a href="#" onclick="showModal(\'password\', {{login:\'{}\'}})">'
                                'click here to set a password!</a>'.format(player.name),
            }))

        asyncio.async(self.send(ws, {'setinfo': player.get_recent_scores()}))
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

        if not text.startswith('!admin'):
            self.chat_scrollback.append(entry)
            if len(self.chat_scrollback) > self.CHAT_SCROLLBACK:
                self.chat_scrollback = self.chat_scrollback[1:]

        logger.info('Chat: {}: {}'.format(player['name'], text))
        asyncio.async(self.trivia.chat(ws, player, text))
