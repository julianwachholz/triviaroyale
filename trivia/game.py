import asyncio
import time
from datetime import datetime
import re
import logging

from .models import *


logger = logging.getLogger(__name__)


class TriviaGame(object):
    """
    The main trivia game.

    """
    STATE_IDLE = 'idle'
    STATE_QUESTION = 'question'
    STATE_WAITING = 'waiting'

    ROUND_TIME = 45.0
    WAIT_TIME = 15.0
    BASE_POINTS = 500
    INACTIVITY_TIMEOUT = ROUND_TIME * 4

    RE_START = re.compile('^!start', re.IGNORECASE)

    def __init__(self, broadcast):
        self.state = self.STATE_IDLE
        self.broadcast = broadcast
        self.queue = asyncio.Queue()
        self.last_action = time.time()
        self.timeout = None
        self.timer_start = None
        self.round = None

    def get_round_info(self):
        elapsed_time = (time.time() - self.timer_start) if self.round else 0
        timer = ''

        if self.state == self.STATE_QUESTION:
            game = ('<p class="question-info">#{round.id}</p>'
                    '<p class="question-categories">{round.question.category_names}</p>'
                    '<p class="question">{round.question.question}</p>').format(round=self.round)

            timer = ('<div class="timer-bar" style="width:{width}%" data-time-left="{time_left}"></div>'
                     '<div class="timer-value"><span>{time_left}</span>s</div>').format(
                width=(self.ROUND_TIME - elapsed_time) / self.ROUND_TIME * 100.0,
                time_left=self.ROUND_TIME - elapsed_time,
            )

        elif self.state == self.STATE_WAITING:
            game = '<p class="question-info">#{round.id}</p>'.format(round=self.round)
            answer = self.round.question.primary_answer

            if self.round.solved:
                game += ('<p><b>{round.solver.name}</b> got '
                         '<b>{round.points}</b> points for answering in <b>{round.time_taken:.2f}s</b>:'
                         '<br>{round.question.question}</p>').format(round=self.round)
                game += '<p>Correct answer:<br><b>{}</b></p>'.format(answer)
            else:
                game += ('<p>{round.question.question}</p><p><b>Time\'s up!</b> '
                         'Nobody got the answer: <b>{answer}</b></p>').format(round=self.round, answer=answer)

            timer = ('<div class="timer-bar colorless" style="width:{width}%" data-time-left="{time_left}"></div>'
                     '<div class="timer-value">Next round in: <span>{time_left}</span>s</div>').format(
                width=(self.WAIT_TIME - elapsed_time) / self.WAIT_TIME * 100.0,
                time_left=self.WAIT_TIME - elapsed_time,
            )

        elif self.state == self.STATE_IDLE:
            game = '<p>Trivia is not running.</p><p>Say <kbd>!start</kbd> to begin a new round.</p>'

        return {
            'game': game,
            'timer': timer,
        }

    @asyncio.coroutine
    def run(self):
        asyncio.async(self.run_chat())

    @asyncio.coroutine
    def chat(self, player, text):
        yield from self.queue.put((player, text))

    @asyncio.coroutine
    def run_chat(self):
        """
        Monitor chat for commands and question answers.

        """
        while True:
            player, text = yield from self.queue.get()
            self.last_action = time.time()

            if self.state == self.STATE_IDLE and self.RE_START.match(text):
                asyncio.async(self.delay_new_round(new_round=True))

            if self.state == self.STATE_QUESTION and self.round.question.check_answer(text):
                asyncio.get_event_loop().call_soon_threadsafe(self.timeout.cancel)
                asyncio.async(self.round_solved(player))

    @asyncio.coroutine
    def round_solved(self, player_name):
        self.state = self.STATE_WAITING
        with db_session():
            player = get(p for p in Player if p.name == player_name)
            played_round = Round[self.round.id]
            played_round.solved_by(player)
            played_round.end_round()
            self.round = played_round
        asyncio.async(self.round_end())

    @asyncio.coroutine
    def delay_new_round(self, new_round=False):
        self.state = self.STATE_WAITING
        wait = self.WAIT_TIME

        if new_round:
            wait = self.WAIT_TIME / 3
            self.round_start = datetime.now()
            asyncio.async(self.broadcast({
                'system': "New round starting in {}s!".format(wait),
            }))

        yield from asyncio.sleep(wait)

        if time.time() - self.last_action > self.INACTIVITY_TIMEOUT:
            self.state = self.STATE_IDLE
            asyncio.async(self.broadcast({
                'system': "Stopping due to inactivity!",
            }))
            self.broadcast_info()
        else:
            asyncio.async(self.start_new_round())

    @asyncio.coroutine
    def start_new_round(self):
        with db_session():
            new_round = Round.new(self.round_start)
            commit()
            self.round = new_round
        self.timeout = asyncio.async(self.round_timeout())
        self.state = self.STATE_QUESTION
        self.timer_start = time.time()
        self.broadcast_info()

    @asyncio.coroutine
    def round_timeout(self):
        yield from asyncio.sleep(self.ROUND_TIME)
        with db_session():
            end_round = Round[self.round.id]
            end_round.end_round()
            self.round = end_round
        asyncio.async(self.round_end())

    @asyncio.coroutine
    def round_end(self):
        self.state = self.STATE_WAITING
        self.timer_start = time.time()
        self.broadcast_info()
        asyncio.async(self.delay_new_round())

    def broadcast_info(self):
        asyncio.async(self.broadcast({
            'setinfo': self.get_round_info(),
        }))
