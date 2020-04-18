import asyncio
import logging
import os
import re
import time

import requests

from trivia.game import TriviaGame
from trivia.models import Player, commit, db_session

logger = logging.getLogger(__name__)


last_notified = None


GOOD_PLACE = {
    re.compile(search): repl
    for search, repl in (
        {
            r"\b(mother)?fuck(ers?|s|ed|ing)?\b": r"\1fork\2",
            r"\b(bull)?shit(s|ting)?\b": r"\1shirt\2",
            r"\bbitch(es)?\b": r"bench\1",
            r"\bass(holes?)?\b": r"ash\1",
            r"\bcock(s|suckers?)?\b": r"cork\1",
            r"\bdick(s|heads?)?\b": r"dink\1",
        }
    ).items()
}


def send_pushover(message):
    app_token = os.getenv("PUSHOVER_APP_TOKEN")
    user_token = os.getenv("PUSHOVER_USER_TOKEN")
    if app_token is not None and user_token is not None:
        logger.info(f"Notifying admin: {message}.")
        url = f"https://api.pushover.net/1/messages.json"
        requests.post(
            url, data={"token": app_token, "user": user_token, "message": message},
        )


async def notify_online_player(name):
    """Send a Pushover notification that a player is online."""
    global last_notified

    delay = 60 * 15  # 15 minutes
    if last_notified is None or last_notified + delay < time.time():
        send_pushover(f"Player {name} is now online!")
        last_notified = time.time()


class GameController(object):
    """
    Controller handles users and interaction with them.

    Login/passwords and chat interaction goes through this.

    """

    CHAT_SCROLLBACK = 50

    COMMANDS = [
        "help",
        "rules",
        "login",
        "admin",
        "vote",
        "start",
        "hint",
        "next",
        "info",
    ]

    HELP = {
        "": [
            "Available commands:",
            "*/help* - This text.",
            "*/rules* - Read the rules.",
            "*/start* - Start a new round.",
            "*/hint* - Request a hint.",
            "*/vote* - Rate a question after a round.",
            "*/next* - Skip to next question.",
            "*/login* - Change nick or password.",
            "*/info* - More info about TriviaRoyale",
            "Use /help _<command>_ for more info.",
            "All commands may also be prefixed with *!* or a dot *.* instead of a slash */*.",
        ],
        "rules": ["*/rules* - Read the game rules."],
        "vote": [
            "*/vote <up|down>* - Rate a question after a round.",
            "Use */++ /good* or */-- /bad* to leave a positive or negative rating respectively.",
        ],
        "start": ["*/start* Start a new round of TriviaRoyale."],
        "hint": [
            "*/hint* Request a new hint for the current question, if possible. Shorthand: */h*",
        ],
        "next": [
            "*/next* Skip the current waiting time between rounds. (Shorthand: */n*)",
            "Only possible if you have a streak of at least 5.",
        ],
        "login": [
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
                asyncio.ensure_future(
                    self.broadcast(
                        {
                            "system": "{} left.".format(player["name"]),
                            "setinfo": self._get_player_info(),
                        }
                    )
                )
                logger.info("Leave: {} (#{})".format(player["name"], player["id"]))
            self.clients.remove(ws)

    def _set_name(self, ws, player_id, name, old_name=None):
        asyncio.ensure_future(self.send(ws, {"setinfo": {"playername": name}}))
        if old_name is None:
            self.trivia.player_count += 1
            asyncio.ensure_future(
                self.broadcast(
                    {
                        "system": "{} joined.".format(name),
                        "setinfo": self._get_player_info(),
                    }
                )
            )
            logger.info("Join: {} (#{})".format(name, player_id))
            asyncio.ensure_future(notify_online_player(name))
        else:
            asyncio.ensure_future(
                self.broadcast(
                    {
                        "system": "{} is now known as *{}*.".format(old_name, name),
                        "setinfo": self._get_player_info(),
                    }
                )
            )
            logger.info("Rename: {} to {} (#{})".format(name, old_name, player_id))

    def _rename_player(self, ws, new_name):
        player = self.players[ws]

        if player["name"] == new_name:
            asyncio.ensure_future(
                self.send(
                    ws, {"system": "You are already known as *{}*.".format(new_name)}
                )
            )
        else:
            with db_session():
                if Player.exists(lambda p: p.name == new_name):
                    asyncio.ensure_future(
                        self.send(
                            ws,
                            {
                                "system": "This name is not available: *{}*.".format(
                                    new_name
                                ),
                            },
                        )
                    )
                else:
                    old_name = player["name"]
                    player["name"] = new_name
                    Player[player["id"]].set(name=new_name)
                    self._set_name(ws, player["id"], new_name, old_name=old_name)

    def _get_player_info(self):
        players = sorted(self.players.values(), key=lambda p: p["joined"])
        count = len(self.players)
        return {
            "playercount": "{} Player{}".format(count, "s" if count != 1 else ""),
            "players": list(map(lambda player: player["name"], players)),
        }

    @db_session
    def _set_password(self, ws, password):
        player = self.players[ws]
        player = Player[self.players[ws]["id"]]
        player.set_password(password)
        asyncio.ensure_future(
            self.send(ws, {"system": "Password successfully changed!"})
        )
        logger.info("Password: {} set new password.".format(player))

    def command(self, ws, command, args):
        if command.startswith("_"):
            logger.warn(
                "Illegal command from {}: {} with {}".format(
                    self.players[ws]["name"], command, args
                )
            )
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
            logger.debug(
                "Ran command from {}: {} with {}".format(
                    self.players[ws]["name"], command, args
                )
            )
        else:
            logger.warn(
                "Unknown command from {}: {} with {}".format(
                    self.players[ws]["name"], command, args
                )
            )

    def help(self, ws, *args, **kwargs):
        if len(args) == 0 or args[0] == "help":
            helptext = self.HELP[""]
        else:
            helptext = self.HELP.get(args[0], ["Unknown command."])
        asyncio.ensure_future(self.send(ws, [{"system": line} for line in helptext]))

    def rules(self, ws, *args, **kwargs):
        rules = [
            "*Game Rules*",
            "1. The first player to answer the current question correctly wins the round. The faster the answer, \
                the more points will be awarded.",
            "2. Collect bonus points by using fewer hints and answering multiple questions correctly in a row.",
            "3. Play honestly and fair, no cheating by looking up answers on Google, Wikipedia etc. or any other medium.\
                This is not a contest on who googles the quickest.",
            "4. Be nice, don't swear or be rude. Site bans will be applied if required.",
        ]
        asyncio.ensure_future(self.send(ws, [{"system": line} for line in rules]))

    def info(self, ws, *args, **kwargs):
        infotext = [
            "This game uses Python and asyncio under the hood.",
            "Find out more on https://github.com/julianwachholz/triviaroyale",
        ]
        asyncio.ensure_future(self.send(ws, [{"system": line} for line in infotext]))

    def vote(self, ws, player_vote, *args, **kwargs):
        if player_vote in ("up", "+"):
            player_vote = 1
        elif player_vote in ("down", "-"):
            player_vote = -1
        if player_vote in (-1, 1):
            try:
                player_name = self.players[ws]["name"]
            except KeyError:
                return
            if self.trivia.queue_vote(player_name, player_vote):
                asyncio.ensure_future(
                    self.send(
                        ws,
                        {
                            "setinfo": {
                                "question-vote": '<p class="question-vote">Thank you!</p>',
                            }
                        },
                    )
                )

    def start(self, ws, *args, **kwargs):
        """
        Start a new round if there is no round running yet.

        """
        logger.info("Start: {}".format(self.players[ws]["name"]))
        self.trivia.timeout = asyncio.ensure_future(self.trivia.delay_new_round(True))

    def hint(self, ws, *args, **kwargs):
        """
        Request a new hint if currently possible.

        """
        self.trivia.get_hint(from_player=self.players[ws]["name"])

    def next(self, ws, *args, **kwargs):
        """
        Skip the current waiting time and go directly to the next question.

        """
        if (
            self.trivia.state == TriviaGame.STATE_WAITING
            and self.trivia.has_streak(self.players[ws])
            and time.time() - self.trivia.timer_start > self.trivia.WAIT_TIME_MIN
        ):
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
                asyncio.ensure_future(
                    self.send(
                        ws,
                        {"prompt": "password", "data": {"login": login, "auto": True}},
                    )
                )
                return
            else:
                asyncio.ensure_future(
                    self.send(
                        ws,
                        {
                            "system": "Invalid username/password!",
                            "system_extra": "<a href=\"#\" onclick=\"showModal('password', {{login:'{}'}})\">"
                            "Try again</a>".format(login),
                        },
                    )
                )
                return

        player.logged_in()

        self.players[ws] = {
            "joined": time.time(),
            "id": player.id,
            "name": player.name,
            "permissions": player.permissions,
        }
        asyncio.ensure_future(self.send(ws, self.chat_scrollback))
        self._set_name(ws, player.id, player.name)

        if not player.has_password():
            asyncio.ensure_future(
                self.send(
                    ws,
                    {
                        "system": "You currently have no password! Your nickname is not protected.",
                        "system_extra": "<a href=\"#\" onclick=\"showModal('password', {{login:'{}'}})\">"
                        "Click here to set a password!</a>".format(player.name),
                    },
                )
            )

        asyncio.ensure_future(self.send(ws, {"setinfo": player.get_recent_scores()}))
        asyncio.ensure_future(self.send(ws, {"setinfo": self.trivia.get_round_info()}))

    def admin(self, ws, *args, **kwargs):
        """
        Issue an admin only command.

        """
        player = self.players[ws]
        if player["permissions"] > 0:
            admin_command = AdminCommand(self.trivia, player["id"])
            admin_command.run(args[0], *args[1:])

    def chat(self, ws, text):
        player = self.players[ws]
        text = self.good_place(text)
        entry = {
            "player": player["name"],
            "text": text,
        }
        asyncio.ensure_future(self.broadcast(entry))
        entry.update(time=int(time.time()))

        if not text.startswith("!admin"):
            self.append_chat_log(entry)

        logger.info("Chat: {}: {}".format(player["name"], text))
        asyncio.ensure_future(self.trivia.chat(ws, player, text))

    def good_place(self, text):
        """This is a good place."""
        for r, repl in GOOD_PLACE.items():
            text = r.sub(repl, text)

        return text

    def append_chat_log(self, entry):
        self.chat_scrollback.append(entry)
        if len(self.chat_scrollback) > self.CHAT_SCROLLBACK:
            self.chat_scrollback = self.chat_scrollback[1:]


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
            logger.info(
                "Player #{} triggered unknown command: {}".format(self.player_id, cmd)
            )

    def next(self, *args):
        self.game.next_round()

    def stop(self, *args):
        self.game.stop_game("Stopped by administrator.", lock="lock" in args)

    def unlock(self, *args):
        self.game.state = TriviaGame.STATE_IDLE
        self.game.broadcast_info()

    def start(self, *args):
        """If game is locked, only this will start it again."""
        self.game.timeout = asyncio.ensure_future(
            self.game.delay_new_round(new_round=True)
        )
