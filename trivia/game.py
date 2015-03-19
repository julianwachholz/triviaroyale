import asyncio
import time
import logging

from .models import *


logger = logging.getLogger(__name__)


class TriviaGame(object):
    """
    The main trivia game.

    """
    def __init__(self, broadcast):
        self.broadcast = broadcast

    def _get_info(self):
        dummy_data = {
            'round_number': self.round_number,
            'categories': 'Science',
            'question': 'What is the name of the protein which lowers the blood sugar level?',
            'time_left': 23.4,
            'total_time': 45.0,
            'current_points': 320,
            'solver_name': 'banzaikitten',
            'points': 320,
            'answer': 'insulin',
        }

        states = [
            'question',
            'round-over',
            'idle',
        ]

        dummy_data['state'] = states[self.round_number % len(states)]
        return dummy_data

    def get_round_info(self):
        info = self._get_info()
        game = ''
        timer = ''
        if info['state'] == 'question':
            game = ('<p class="question-info">#{round_number}</p>'
                    '<p class="question-categories">{categories}</p>'
                    '<p class="question">{question}</p>').format(**info)
            timer = ('<div class="timer-bar" style="width:{width}%" data-time-left="{time_left}"></div>'
                     '<div class="timer-value">{points}</div>').format(
                width=info['time_left'] / info['total_time'] * 100.0,
                time_left=info['time_left'],
                points=info['current_points'],
            )
        elif info['state'] == 'round-over':
            game = '<p class="question-info">#{round_number}</p>'.format(**info)
            if info['solver_name']:
                game += ('<p><strong>{solver_name}</strong> got '
                         '<strong>{points} points</strong> for answering:<br>{question}</p>').format(**info)
            else:
                game += ('<p>{question}</p>'
                         '<p><strong>Time\'s up!</strong> Nobody got the answer.</p>').format(**info)
            game += '<p>Correct answer:<br><strong>{answer}</strong></p>'.format(**info)
        else:
            game = '<p>Status: {state}</p>'.format(**info)

        return {
            'game': game,
            'timer': timer,
        }

    @asyncio.coroutine
    def run(self):
        self.round_number = 0
        while True:
            self.round_number += 1
            asyncio.async(self.broadcast({
                'system': "Trivia is running: #{}".format(self.round_number),
            }))
            yield from asyncio.sleep(5.0)
