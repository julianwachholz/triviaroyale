import asyncio
import logging
import math
import time
from datetime import datetime

from .models import Player, Question, Round, commit, db_session

logger = logging.getLogger(__name__)


class TriviaGame(object):
    """
    The main trivia game.

    """

    STATE_IDLE = "idle"
    STATE_STARTING = "starting"
    STATE_QUESTION = "question"
    STATE_WAITING = "waiting"
    STATE_LOCKED = "locked"

    ROUND_TIME = 45.0
    WAIT_TIME = 15.0
    WAIT_TIME_NEW_ROUND = 10.0
    WAIT_TIME_MIN = 2.5
    WAIT_TIME_EXTRA = 20.0  # When showing additional info after a round
    INACTIVITY_TIMEOUT = ROUND_TIME * 3

    STREAK_STEPS = 5
    HINT_TIMING = 10.0
    HINT_COOLDOWN = 1.0
    HINT_MAX = 3

    def __init__(self, broadcast, send):
        self.state = self.STATE_IDLE
        self.broadcast = broadcast
        self.send = send
        self.queue = asyncio.Queue()
        self.last_action = time.time()
        self.timeout = None
        self.timer_start = None
        self.round = None
        self.player_count = 0
        self._reset_hints()
        self._reset_streak()
        self._reset_votes()

    def get_round_info(self):
        elapsed_time = (time.time() - self.timer_start) if self.timer_start else 0
        timer = ""

        if self.state == self.STATE_QUESTION:
            game = (
                '<p class="question-info">#{round.id}</p>'
                '<p class="question-categories">{round.question.category_names}</p>'
                '<p class="question">{round.question.question}</p>'
            ).format(round=self.round)

            if self.hints["current"] is not None:
                game += '<p class="question-hint">{}</p>'.format(self.hints["current"])

            if self.hint_available(ignore_cooldown=True):
                game += '<p><button class="tiny z2" onclick="command(\'hint\')">Get hint</button></p>'

            timer = (
                '<div class="timer-bar" style="width:{width}%" '
                'data-total-time="{total_time}" data-time-left="{time_left}"></div>'
                '<div class="timer-value"><span>{time_left:.2f}</span>s</div>'
            ).format(
                width=(self.ROUND_TIME - elapsed_time) / self.ROUND_TIME * 100.0,
                total_time=self.ROUND_TIME,
                time_left=self.ROUND_TIME - elapsed_time,
            )

        elif self.state == self.STATE_WAITING:
            game = '<p class="question-info">#{round.id}</p>'.format(round=self.round)
            answer = self.round.question.primary_answer

            if self.round.solved:
                game += (
                    "<p><b>{round.solver.name}</b> got "
                    "<b>{round.points}</b> points for answering in <b>{round.time_taken:.2f}s</b>: "
                    "<br>{round.question.question}</p>"
                ).format(round=self.round)
                game += "<p>Correct answer: <b>{}</b></p>".format(answer)
            else:
                game += (
                    "<p>{round.question.question}</p><p><b>Time's up!</b> "
                    "Nobody got the answer: <b>{answer}</b></p>"
                ).format(round=self.round, answer=answer)

            game += (
                '<p id="question-vote" class="question-vote">'
                '<button class="tiny positive z2" onclick="command(\'vote\', 1)">Good Question</button>'
                '<button class="tiny negative z2" onclick="command(\'vote\', -1)">Bad Question</button></p>'
            )

            timer = (
                '<div class="timer-bar colorless" style="width:{width}%" data-time-left="{time_left}"></div>'
                '<div class="timer-value">Next round in: <span>{time_left}</span>s</div>'
            ).format(
                width=(self.WAIT_TIME - elapsed_time) / self.WAIT_TIME * 100.0,
                time_left=self.WAIT_TIME - elapsed_time,
            )

        elif self.state == self.STATE_IDLE:
            game = (
                "<p>TriviaRoyale is not running.</p>"
                '<p><button class="z4" onclick="command(\'start\')">Start new round</button></p>'
                '<p>Coming soon: <strong>TriviaRoyale 2.0!</strong></p>'
                '<p class="flex center"><a target="_blank" href="https://twitter.com/triviaroyaleio" class="button tiny inline-flex">'
                '<svg width="16" height="16" fill="currentColor" class="btn-icon" viewBox="0 0 24 24"><path d="M24 4.6a10 10 0 0 1-2.9.7 5 5 0 0 0 2.2-2.7c-1 .6-2 1-3.1 1.2a5 5 0 0 0-8.4 4.5A14 14 0 0 1 1.6 3.2 4.8 4.8 0 0 0 1 5.6a5 5 0 0 0 2.2 4.1 4.9 4.9 0 0 1-2.3-.6A5 5 0 0 0 5 14a5 5 0 0 1-2.2 0 5 5 0 0 0 4.6 3.5 9.9 9.9 0 0 1-6.1 2.1H0a14 14 0 0 0 7.6 2.2c9 0 14-7.5 14-14V7A10 10 0 0 0 24 4.6z"/></svg>'
                'Follow on Twitter</a><a target="_blank" href="https://beta.triviaroyale.io/blog/subscribe/" class="button tiny inline-flex">'
                '<svg width="16" height="16" class="btn-icon" viewBox="0 0 20 20" fill="currentColor"><path d="M2.003 5.884L10 9.882l7.997-3.998A2 2 0 0016 4H4a2 2 0 00-1.997 1.884z" /><path d="M18 8.118l-8 4-8-4V14a2 2 0 002 2h12a2 2 0 002-2V8.118z" /></svg>'
                "Subscribe to newsletter</a></p>"
            )

        elif self.state == self.STATE_STARTING:
            game = "<p>New round starting in a few seconds...</p>"
            timer = (
                '<div class="timer-bar colorless" style="width:{width}%" data-time-left="{time_left}"></div>'
                '<div class="timer-value">Starting in: <span>{time_left}</span>s</div>'
            ).format(
                width=(self.WAIT_TIME_NEW_ROUND - elapsed_time)
                / self.WAIT_TIME_NEW_ROUND
                * 100.0,
                time_left=self.WAIT_TIME_NEW_ROUND - elapsed_time,
            )

        elif self.state == self.STATE_LOCKED:
            game = "<p>TriviaRoyale is stopped.</p><p>Only an administrator can start it.</p>"

        return {
            "game": game,
            "timer": timer,
        }

    async def run(self):
        asyncio.ensure_future(self.run_chat())

    async def chat(self, ws, player, text):
        await self.queue.put((ws, player, text))

    async def run_chat(self):
        """
        Monitor chat for commands and question answers.

        """
        while True:
            ws, player, text = await self.queue.get()
            self.last_action = time.time()

            if self.state == self.STATE_QUESTION:
                if self.round.question.check_answer(text):
                    asyncio.get_event_loop().call_soon_threadsafe(self.timeout.cancel)
                    asyncio.ensure_future(self.round_solved(ws, player))

    async def round_solved(self, ws, player):
        self.state = self.STATE_WAITING
        if self.streak["player_id"] == player["id"]:
            self.streak["count"] += 1
            self.streak["player_name"] = player["name"]
            if self.streak["count"] % self.STREAK_STEPS == 0:
                self.announce_streak(player["name"])
        else:
            if self.streak["count"] >= self.STREAK_STEPS:
                self.announce_streak(player["name"], broken=True)
            self.streak = {
                "player_id": player["id"],
                "player_name": player["name"],
                "count": 1,
            }

        with db_session():
            player_db = Player.get(lambda p: p.name == player["name"])
            played_round = Round[self.round.id]
            played_round.solved_by(
                player_db,
                self.ROUND_TIME,
                hints=self.hints["count"],
                streak=self.streak["count"],
            )
            played_round.end_round()
            self.round = played_round

        asyncio.ensure_future(
            self.send(
                ws,
                {
                    "setinfo": player_db.get_recent_scores(),
                    # track conversion goal for round solved
                    "log_event": ["trackGoal", 1],
                },
            )
        )

        asyncio.ensure_future(self.round_end())
        logger.info(
            "#{} END: {} for {} points ({} hints used) in {:.2f}s: {}".format(
                self.round.id,
                self.round.solver,
                self.round.points,
                self.hints["count"],
                self.round.time_taken,
                self.round.question,
            )
        )

    def next_round(self):
        """
        Skip to the next round.

        """
        if self.state == self.STATE_WAITING and self.timeout is not None:
            asyncio.get_event_loop().call_soon_threadsafe(self.timeout.cancel)
            asyncio.ensure_future(self.start_new_round())

    def stop_game(self, reason=None, lock=False):
        """
        Stop the game immediately no matter what.

        """
        if self.timeout is not None:
            asyncio.get_event_loop().call_soon_threadsafe(self.timeout.cancel)
        if lock:
            self.state = self.STATE_LOCKED
        else:
            self.state = self.STATE_IDLE

        asyncio.ensure_future(
            self.broadcast({"system": reason or "Stopping due to inactivity!",})
        )
        self.broadcast_info()

    async def delay_new_round(self, new_round=False):
        if self.state == self.STATE_STARTING:
            logger.warn("Preventing multiple simultaneous games!")
            return

        wait = self.WAIT_TIME

        if new_round:
            self.last_action = time.time()
            self.state = self.STATE_STARTING
            wait = self.WAIT_TIME_NEW_ROUND
            self.timer_start = time.time()
            self.round_start = datetime.utcnow()
            self._reset_streak()
            self.broadcast_info()
        else:
            self.state = self.STATE_WAITING

        await asyncio.sleep(wait)

        if (
            self.player_count < 1
            or time.time() - self.last_action > self.INACTIVITY_TIMEOUT
        ):
            self.stop_game()
            logger.info(
                "No activity, stopping game. ({} players online, {:.2f}s)".format(
                    self.player_count, time.time() - self.last_action
                )
            )
        else:
            asyncio.ensure_future(self.start_new_round())

    async def start_new_round(self):
        self.save_votes()

        with db_session():
            try:
                new_round = Round.new(self.round_start)
            except IndexError:
                self.round_start = datetime.utcnow()
                new_round = Round.new(self.round_start)
            commit()
            self.round = new_round
        timeout = asyncio.ensure_future(self.round_timeout())
        asyncio.ensure_future(self.broadcast_update(timeout))

        self.timeout = timeout
        self.state = self.STATE_QUESTION
        self.timer_start = time.time()
        self._reset_hints()
        self._reset_votes()
        self.announce("Round #{}".format(self.round.id))
        self.broadcast_info()

    async def round_timeout(self):
        """
        If this future isn't canceled the round will end with no winner.

        """
        await asyncio.sleep(self.ROUND_TIME)
        with db_session():
            end_round = Round[self.round.id]
            end_round.end_round()
            self.round = end_round
        logger.info("#{} END: NO WINNER: {}".format(self.round.id, self.round.question))
        asyncio.ensure_future(self.round_end())

    async def round_end(self):
        self.state = self.STATE_WAITING
        self.timer_start = time.time()
        self.broadcast_info()
        self.timeout = asyncio.ensure_future(self.delay_new_round())

    async def broadcast_update(self, fut, num=1):
        """
        Periodically update the game info to all clients.
        Mainly used to announce new hint availability.

        :param fut: Current round timeout future.

        """
        await asyncio.sleep(self.HINT_TIMING)
        if fut.cancelled():
            return

        self.broadcast_info()

        if num + 1 < self.HINT_MAX:
            asyncio.ensure_future(self.broadcast_update(fut, num + 1))

    def broadcast_info(self):
        asyncio.ensure_future(self.broadcast({"setinfo": self.get_round_info(),}))

    def announce(self, message):
        asyncio.ensure_future(self.broadcast({"system": message, "announce": True,}))

    def _reset_streak(self):
        self.streak = {
            "count": 0,
            "player_name": None,
            "player_id": None,
        }

    def has_streak(self, player):
        return (
            self.streak["player_id"] == player["id"]
            and self.streak["count"] >= self.STREAK_STEPS
        )

    def announce_streak(self, player_name, broken=False):
        streak = self.streak["count"]
        if broken:
            info = "{} broke {}'s streak of *{}*!".format(
                player_name, self.streak["player_name"], streak
            )
            logger.info(
                "#{} STREAK BREAK: {} broke {} ({})".format(
                    self.round.id, player_name, self.streak["player_name"], streak
                )
            )
        else:
            info = "{} has reached a streak of *{}*!".format(player_name, streak)
            logger.info(
                "#{} STREAK: {} has {}".format(self.round.id, player_name, streak)
            )
            if streak == self.STREAK_STEPS:
                info += " You can skip to the next round with *!next*"
        asyncio.ensure_future(self.broadcast({"system": info,}))

    def _reset_hints(self):
        self.hints = {
            "count": 0,
            "current": None,
            "time": 0,
            "cooldown": 0,
        }

    def hint_available(self, ignore_cooldown=False):
        if self.state != self.STATE_QUESTION or self.hints["count"] >= self.HINT_MAX:
            return False

        now = time.time()
        elapsed_time = now - self.timer_start
        current_max_hints = math.ceil(elapsed_time / self.HINT_TIMING)

        if not ignore_cooldown and now - self.hints["time"] < self.HINT_COOLDOWN:
            return False

        if current_max_hints > self.hints["count"]:
            return True
        return False

    def get_hint(self, from_player=None):
        if self.state != self.STATE_QUESTION or self.hints["count"] >= self.HINT_MAX:
            return

        if self.hint_available():
            logger.info("#{} HINT: {}".format(self.round.id, from_player))
            self.hints["time"] = time.time()
            self.hints["count"] += 1
            self.hints["current"] = self.round.question.get_hint(self.hints["count"])
            self.broadcast_info()

    def _reset_votes(self):
        self.votes = {
            "players": set(),
            "up": 0,
            "down": 0,
        }

    def queue_vote(self, player_name, value):
        """
        Try to queue a vote during the waiting phase between rounds.

        """
        if self.state != self.STATE_WAITING or self.round is None:
            return False

        if player_name not in self.votes["players"]:
            self.votes["players"].add(player_name)
            if value == 1:
                self.votes["up"] += 1
            elif value == -1:
                self.votes["down"] += 1
            return True
        return False

    def save_votes(self):
        if self.round is not None:
            logger.info(
                "#{} VOTES: +{} -{} by {}".format(
                    self.round.id,
                    self.votes["up"],
                    self.votes["down"],
                    ", ".join(self.votes["players"]),
                )
            )
            with db_session():
                q = Question[self.round.question.id]
                q.set(
                    vote_up=q.vote_up + self.votes["up"],
                    vote_down=q.vote_down + self.votes["down"],
                )
