import asyncio
import time
import math
import re
import logging
from datetime import datetime

from .models import Round, Player, Question, db_session, commit


logger = logging.getLogger(__name__)


class TriviaGame(object):
    """
    The main trivia game.

    """
    STATE_IDLE = 'idle'
    STATE_STARTING = 'starting'
    STATE_QUESTION = 'question'
    STATE_WAITING = 'waiting'
    STATE_LOCKED = 'locked'

    ROUND_TIME = 45.0
    WAIT_TIME = 10.0
    WAIT_TIME_MIN = 2.5
    WAIT_TIME_EXTRA = 7.0  # When showing additional info after a round
    INACTIVITY_TIMEOUT = ROUND_TIME * 4

    STREAK_STEPS = 5
    HINT_TIMING = 10.0
    HINT_COOLDOWN = 2.5
    HINT_MAX = 3

    RE_START = re.compile(r'^!start', re.I)
    RE_HINT = re.compile(r'^!h(int)?', re.I)
    RE_NEXT = re.compile(r'^!n(ext)?', re.I)

    RE_ADMIN = re.compile(r'^!a(?:dmin)? (\S+) ?(.*?)$', re.I)

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
        elapsed_time = (time.time() - self.timer_start) if self.round else 0
        timer = ''

        if self.state == self.STATE_QUESTION:
            game = ('<p class="question-info">#{round.id}</p>'
                    '<p class="question-categories">{round.question.category_names}</p>'
                    '<p class="question">{round.question.question}</p>').format(round=self.round)

            if self.hints['current'] is not None:
                game += '<p class="question-hint">{}</p>'.format(self.hints['current'])

            game += '<p><button class="tiny z2" onclick="command(\'hint\')">Get hint</button></p>'

            timer = ('<div class="timer-bar" style="width:{width}%" '
                     'data-total-time="{total_time}" data-time-left="{time_left}"></div>'
                     '<div class="timer-value"><span>{time_left:.2f}</span>s</div>').format(
                width=(self.ROUND_TIME - elapsed_time) / self.ROUND_TIME * 100.0,
                total_time=self.ROUND_TIME,
                time_left=self.ROUND_TIME - elapsed_time,
            )

        elif self.state == self.STATE_WAITING:
            game = '<p class="question-info">#{round.id}</p>'.format(round=self.round)
            answer = self.round.question.primary_answer

            if self.round.solved:
                game += ('<p><b>{round.solver.name}</b> got '
                         '<b>{round.points}</b> points for answering in <b>{round.time_taken:.2f}s</b>:'
                         '<br>{round.question.question}</p>').format(round=self.round)
                game += '<p>Correct answer: <b>{}</b></p>'.format(answer)
            else:
                game += ('<p>{round.question.question}</p><p><b>Time\'s up!</b> '
                         'Nobody got the answer: <b>{answer}</b></p>').format(round=self.round, answer=answer)

            game += ('<p id="question-vote" class="question-vote">'
                     '<button class="tiny positive z2" onclick="command(\'vote\', 1)">Good Question</button>'
                     '<button class="tiny negative z2" onclick="command(\'vote\', -1)">Bad Question</button></p>')

            timer = ('<div class="timer-bar colorless" style="width:{width}%" data-time-left="{time_left}"></div>'
                     '<div class="timer-value">Next round in: <span>{time_left}</span>s</div>').format(
                width=(self.WAIT_TIME - elapsed_time) / self.WAIT_TIME * 100.0,
                time_left=self.WAIT_TIME - elapsed_time,
            )

        elif self.state == self.STATE_IDLE:
            game = ('<p>Trivia is not running.</p>'
                    '<p><button class="z4" onclick="command(\'start\')">Start new round</button></p>')

        elif self.state == self.STATE_STARTING:
            game = '<p>New round starting in a few seconds...</p>'

        elif self.state == self.STATE_LOCKED:
            game = '<p>Trivia is stopped.</p><p>Only an administrator can start it.</p>'

        return {
            'game': game,
            'timer': timer,
        }

    @asyncio.coroutine
    def run(self):
        asyncio.async(self.run_chat())

    @asyncio.coroutine
    def chat(self, ws, player, text):
        yield from self.queue.put((ws, player, text))

    @asyncio.coroutine
    def run_chat(self):
        """
        Monitor chat for commands and question answers.

        """
        while True:
            ws, player, text = yield from self.queue.get()
            self.last_action = time.time()

            if self.RE_ADMIN.search(text) and player['permissions'] > 0:
                match = self.RE_ADMIN.match(text)
                admin = AdminCommand(self, player['id'])
                admin.run(match.group(1), *match.group(2).split())
                continue

            if self.state == self.STATE_QUESTION:
                if self.round.question.check_answer(text):
                    asyncio.get_event_loop().call_soon_threadsafe(self.timeout.cancel)
                    asyncio.async(self.round_solved(ws, player))
                elif self.RE_HINT.search(text):
                    self.get_hint(player)

            if self.state == self.STATE_WAITING:
                if self.RE_NEXT.search(text) and self.has_streak(player) and \
                   time.time() - self.timer_start > self.WAIT_TIME_MIN:
                        self.next_round()

            if self.state == self.STATE_IDLE:
                if self.RE_START.search(text):
                    self.timeout = asyncio.async(self.delay_new_round(new_round=True))
                    logger.info('{}(#{}) started new round'.format(player['name'], player['id']))

    @asyncio.coroutine
    def round_solved(self, ws, player):
        self.state = self.STATE_WAITING
        if self.streak['player_id'] == player['id']:
            self.streak['count'] += 1
            self.streak['player_name'] = player['name']
            if self.streak['count'] % self.STREAK_STEPS == 0:
                self.announce_streak(player['name'])
        else:
            if self.streak['count'] >= self.STREAK_STEPS:
                self.announce_streak(player['name'], broken=True)
            self.streak = {
                'player_id': player['id'],
                'player_name': player['name'],
                'count': 1,
            }

        with db_session():
            player_db = Player.get(lambda p: p.name == player['name'])
            played_round = Round[self.round.id]
            played_round.solved_by(
                player_db,
                self.ROUND_TIME,
                hints=self.hints['count'],
                streak=self.streak['count']
            )
            played_round.end_round()
            self.round = played_round

        asyncio.async(self.send(ws, {'setinfo': player_db.get_recent_scores()}))

        asyncio.async(self.round_end())
        logger.info('#{} END: {} for {} points ({} hints used) in {:.2f}s: {}'.format(
            self.round.id, self.round.solver, self.round.points, self.hints['count'],
            self.round.time_taken, self.round.question))

    def next_round(self):
        """
        Skip to the next round.

        """
        if self.state == self.STATE_WAITING and self.timeout is not None:
            asyncio.get_event_loop().call_soon_threadsafe(self.timeout.cancel)
            asyncio.async(self.start_new_round())

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

        asyncio.async(self.broadcast({
            'system': reason or "Stopping due to inactivity!",
        }))
        self.broadcast_info()

    @asyncio.coroutine
    def delay_new_round(self, new_round=False):
        if self.state == self.STATE_STARTING:
            logger.warn('Preventing multiple simultaneous games!')
            return

        wait = self.WAIT_TIME

        if new_round:
            self.last_action = time.time()
            self.state = self.STATE_STARTING
            wait = self.WAIT_TIME / 2
            self.round_start = datetime.now()
            self._reset_streak()
            asyncio.async(self.broadcast({
                'system': "New round starting in {:.2f}s!".format(wait),
            }))
            self.broadcast_info()
        else:
            self.state = self.STATE_WAITING

        yield from asyncio.sleep(wait)

        if self.player_count < 1 or time.time() - self.last_action > self.INACTIVITY_TIMEOUT:
            self.stop_game()
            logger.info('No activity, stopping game. ({} players online, {:.2f}s)'.format(
                self.player_count, time.time() - self.last_action))
        else:
            asyncio.async(self.start_new_round())

    @asyncio.coroutine
    def start_new_round(self):
        self.save_votes()

        with db_session():
            try:
                new_round = Round.new(self.round_start)
            except IndexError:
                self.round_start = datetime.now()
                new_round = Round.new(self.round_start)
            commit()
            self.round = new_round
        self.timeout = asyncio.async(self.round_timeout())
        self.state = self.STATE_QUESTION
        self.timer_start = time.time()
        self._reset_hints()
        self._reset_votes()
        self.announce('Round #{}'.format(self.round.id))
        self.broadcast_info()

    @asyncio.coroutine
    def round_timeout(self):
        """
        If this future isn't canceled the round will end with no winner.

        """
        yield from asyncio.sleep(self.ROUND_TIME)
        with db_session():
            end_round = Round[self.round.id]
            end_round.end_round()
            self.round = end_round
        logger.info('#{} END NO WINNER: {}'.format(self.round.id, self.round.question))
        asyncio.async(self.round_end())

    @asyncio.coroutine
    def round_end(self):
        self.state = self.STATE_WAITING
        self.timer_start = time.time()
        self.broadcast_info()
        self.timeout = asyncio.async(self.delay_new_round())

    def broadcast_info(self):
        asyncio.async(self.broadcast({
            'setinfo': self.get_round_info(),
        }))

    def announce(self, message):
        asyncio.async(self.broadcast({
            'system': message,
            'announce': True,
        }))

    def _reset_streak(self):
        self.streak = {
            'count': 0,
            'player_name': None,
            'player_id': None,
        }

    def has_streak(self, player):
        return self.streak['player_id'] == player['id'] and self.streak['count'] >= self.STREAK_STEPS

    def announce_streak(self, player_name, broken=False):
        streak = self.streak['count']
        if broken:
            info = "{} broke {}'s streak of *{}*!".format(player_name, self.streak['player_name'], streak)
        else:
            info = "{} has reached a streak of *{}*!".format(player_name, streak)
            if streak == self.STREAK_STEPS:
                info += " You can skip to the next round with *!next*"
        logger.info('#{} STREAK: {}'.format(self.round.id, info))
        asyncio.async(self.broadcast({
            'system': info,
        }))

    def _reset_hints(self):
        self.hints = {
            'count': 0,
            'current': None,
            'time': 0,
            'cooldown': 0,
        }

    def get_hint(self, from_player=None):
        if self.state != self.STATE_QUESTION or self.hints['count'] >= self.HINT_MAX:
            return

        now = time.time()
        elapsed_time = now - self.timer_start
        current_max_hints = math.ceil(elapsed_time / self.HINT_TIMING)

        if now - self.hints['time'] < self.HINT_COOLDOWN:
            return

        if current_max_hints > self.hints['count']:
            logger.info('HINT REQUEST: {}'.format(from_player))
            self.hints['time'] = now
            self.hints['count'] += 1
            self.hints['current'] = self.round.question.get_hint(self.hints['count'])
            self.broadcast_info()

    def _reset_votes(self):
        self.votes = {
            'players': set(),
            'up': 0,
            'down': 0,
        }

    def queue_vote(self, player_name, value):
        """
        Try to queue a vote during the waiting phase between rounds.

        """
        if self.state != self.STATE_WAITING or self.round is None:
            return False

        if player_name not in self.votes['players']:
            self.votes['players'].add(player_name)
            if value == 1:
                self.votes['up'] += 1
            elif value == -1:
                self.votes['down'] += 1
            return True
        return False

    def save_votes(self):
        if self.round is not None:
            logger.info("#{} VOTES: +{} -{} by {!r}".format(
                self.round.id, self.votes['up'], self.votes['down'], self.votes['players']))
            with db_session():
                q = Question[self.round.question.id]
                q.set(
                    vote_up=q.vote_up + self.votes['up'],
                    vote_down=q.vote_down + self.votes['down']
                )


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
        self.game.timeout = asyncio.async(self.game.delay_new_round(new_round=True))
