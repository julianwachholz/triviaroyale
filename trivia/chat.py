import asyncio
import time
import logging

from trivia.game import TriviaGame
from trivia.models import Player, db_session, commit


logger = logging.getLogger(__name__)


class GameController(object):
    """
    Controller handles users and interaction with them.

    Login/passwords and chat interaction goes through this.

    """
    CHAT_SCROLLBACK = 30

    COMMANDS = [
        'help',
        'login',
        'admin',
        'vote',
        'start',
        'hint',
        'next',
        'info',
    ]

    HELP = {
        '': [
            "Available commands:", 
            "*/help* - This text.", 
            "*/start* - Start a new round.",
            "*/hint* - Request a hint.", 
            "*/next* - Skip to next question.",
            "*/login* - Change nick or password.", 
            "*/info* - More info about trivia.ju.io",
            "Use /help _<command>_ for more info.",
            "All commands may also be prefixed with *!* instead of a slash */*.",
        ],
        'vote': [
            "*/vote* - Rate a question after a round.",
            "Use */++* or */--* to leave a positive of negative rating respectively.",
        ],
        'start': [
            "*/start* Start a new round of Trivia.",
        ],
        'hint': [
            "*/hint* Request a new hint for the current question, if possible. Shorthand: */h*",
        ],
        'next': [
            "*/next* Skip the current waiting time between rounds.",
            "Only possible if you have a streak of at least 5.",
        ],
        'login': [
            "*/login* _<nick>_ or */login* password <password>_", 
            "You may change your player name with this.",
            "If you change your password, you will need to enter it again the next time you log in.",
        ],
    }

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
                asyncio.ensure_future(self.broadcast({
                    'system': "{} left.".format(player['name']),
                    'setinfo': self._get_player_info(),
                }))
                logger.info('Leave: {} (#{})'.format(player['name'], player['id']))
            self.clients.remove(ws)

    def _set_name(self, ws, player_id, name, old_name=None):
        asyncio.ensure_future(self.send(ws, {'setinfo': {
            'playername': name,
        }}))
        if old_name is None:
            self.trivia.player_count += 1
            asyncio.ensure_future(self.broadcast({
                'system': "{} joined.".format(name),
                'setinfo': self._get_player_info(),
            }))
            logger.info('Join: {} (#{})'.format(name, player_id))
        else:
            asyncio.ensure_future(self.broadcast({
                'system': "{} is now known as *{}*.".format(old_name, name),
                'setinfo': self._get_player_info(),
            }))
            logger.info('Rename: {} to {} (#{})'.format(name, old_name, player_id))

    def _rename_player(self, ws, new_name):
        player = self.players[ws]

        if player['name'] == new_name:
            asyncio.ensure_future(self.send(ws, {
                'system': 'You are already known as *{}*.'.format(new_name),
            }))
        else:
            with db_session():
                if Player.exists(lambda p: p.name == new_name):
                    asyncio.ensure_future(self.send(ws, {
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
        asyncio.ensure_future(self.send(ws, {
            'system': 'Password successfully changed!',
        }))
        logger.info('Password: {} set new password.'.format(player))

    def command(self, ws, command, args):
        if command.startswith('_'):
            logger.warn('Illegal command from {}: {} with {}'.format(self.players[ws]['name'], command, args))
            return

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
            logger.debug('Ran command from {}: {} with {}'.format(self.players[ws]['name'], command, args))
        else:
            logger.warn('Unknown command from {}: {} with {}'.format(self.players[ws]['name'], command, args))

    def help(self, ws, *args, **kwargs):
        if len(args) == 0 or args[0] == 'help':
            helptext = self.HELP['']
        else:
            helptext = self.HELP.get(args[0], ["Unknown command."])
        asyncio.ensure_future(self.send(ws, [{'system': line} for line in helptext]))

    def info(self, ws, *args, **kwargs):
        infotext = [
            'This game uses Python and asyncio under the hood.',
            'Find out more on https://github.com/julianwachholz/trivia.ju.io',
        ]
        asyncio.ensure_future(self.send(ws, [{'system': line} for line in infotext]))

    def vote(self, ws, player_vote, *args, **kwargs):
        if player_vote in (-1, 1):
            try:
                player_name = self.players[ws]['name']
            except KeyError:
                return
            if self.trivia.queue_vote(player_name, player_vote):
                asyncio.ensure_future(self.send(ws, {'setinfo': {
                    'question-vote': '<p class="question-vote">Thank you!</p>',
                }}))

    def start(self, ws, *args, **kwargs):
        """
        Start a new round if there is no round running yet.

        """
        logger.info('Start: {}'.format(self.players[ws]['name']))
        self.trivia.timeout = asyncio.ensure_future(self.trivia.delay_new_round(True))

    def hint(self, ws, *args, **kwargs):
        """
        Request a new hint if currently possible.

        """
        self.trivia.get_hint(from_player=self.players[ws]['name'])

    def next(self, ws, *args, **kwargs):
        """
        Skip the current waiting time and go directly to the next question.

        """
        if self.trivia.state == TriviaGame.STATE_WAITING and self.trivia.has_streak(self.players[ws]['name']) and \
           time.time() - self.trivia.timer_start > self.trivia.WAIT_TIME_MIN:
                self.trivia.next_round()

    @db_session
    def login(self, ws, login=None, password=None, *, auto=False, **kwargs):
        """
        Register a player, set and change password and change nickname multi-function.

        """
        if login is None or len(login) > Player.NAME_MAX_LEN:
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
                asyncio.ensure_future(self.send(ws, {
                    'prompt': 'password',
                    'data': {'login': login, 'auto': True},
                }))
                return
            else:
                asyncio.ensure_future(self.send(ws, {
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
            asyncio.ensure_future(self.send(ws, {
                'system': 'You currently have no password!',
                'system_extra': '<a href="#" onclick="showModal(\'password\', {{login:\'{}\'}})">'
                                'click here to set a password!</a>'.format(player.name),
            }))

        asyncio.ensure_future(self.send(ws, {'setinfo': player.get_recent_scores()}))
        asyncio.ensure_future(self.send(ws, {'setinfo': self.trivia.get_round_info()}))
        asyncio.ensure_future(self.send(ws, self.chat_scrollback))

    def admin(self, ws, *args, **kwargs):
        """
        Issue an admin only command.

        """
        player = self.players[ws]
        if player['permissions'] > 0:
            admin_command = AdminCommand(self.trivia, player['id'])
            admin_command.run(args[0], *args[1:])

    def chat(self, ws, text):
        player = self.players[ws]
        entry = {
            'player': player['name'],
            'text': text,
        }
        asyncio.ensure_future(self.broadcast(entry))
        entry.update(time=int(time.time()))

        if not text.startswith('!admin'):
            self.chat_scrollback.append(entry)
            if len(self.chat_scrollback) > self.CHAT_SCROLLBACK:
                self.chat_scrollback = self.chat_scrollback[1:]

        logger.info('Chat: {}: {}'.format(player['name'], text))
        asyncio.ensure_future(self.trivia.chat(ws, player, text))


class AdminCommand(object):
    """
    Run an administrative command.

    """
    def __init__(self, game, player_id):
        self.game = game
        self.player_id = player_id

    def run(self, cmd, *args):
        if hasattr(self, cmd):
            with db_session():
                player = Player[self.player_id]
                if player.has_perm(cmd):
                    logger.info("{} executed: {}({!r})".format(player.name, cmd, args))
                    return getattr(self, cmd)(self, *args)
                else:
                    logger.warn("{} has no access to: {}".format(player, cmd))
        else:
            logger.info("Player #{} triggered unknown command: {}".format(self.player_id, cmd))

    def next(self, *args):
        self.game.next_round()

    def stop(self, *args):
        self.game.stop_game("Stopped by administrator.", lock='lock' in args)

    def unlock(self, *args):
        self.game.state = TriviaGame.STATE_IDLE
        self.game.broadcast_info()

    def start(self, *args):
        """If game is locked, only this will start it again."""
        self.game.timeout = asyncio.ensure_future(self.game.delay_new_round(new_round=True))
