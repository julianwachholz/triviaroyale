import os
import re
import time
from datetime import datetime, timedelta

from pony.orm import *
from passlib.hash import bcrypt_sha256


db = Database()
sql_debug(bool(os.environ.get('DEBUG', False)))


class Category(db.Entity):
    """
    Questions should have at least one category.

    """
    name = Required(str, 25, unique=True)
    questions = Set('Question')


class Question(db.Entity):
    """
    Question objects.

    Multiple answers are separated using "|"

    """
    active = Required(bool, default=False)

    question = Required(str, 200)
    media_url = Optional(str, 500)
    answer = Required(str, 200)

    categories = Set(Category)
    additional_info = Optional(str)

    times_played = Required(int, default=0)
    times_solved = Required(int, default=0)

    date_added = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    date_modified = Optional(datetime)
    last_played = Optional(datetime)

    rounds = Set('Round')
    reports = Set('Report')
    player = Optional('Player')

    @property
    def primary_answer(self):
        return self.answer.split('|')[0]

    @property
    def answer_re(self):
        if not hasattr(self, '_answer_re'):
            pattern = r'\b{}\b'.format(self.answer)
            self._answer_re = re.compile(pattern, re.IGNORECASE)
        return self._answer_re

    @property
    def category_names(self):
        if not hasattr(self, '_category_names'):
            with db_session():
                self._category_names = ', '.join([c.name for c in self.categories.order_by(Category.name)])
        return self._category_names

    @property
    def solve_percentage(self):
        if self.times_played == 0:
            return 0
        return self.times_solved / self.times_played * 100

    def check_answer(self, answer):
        return self.answer_re.search(answer) is not None


class Player(db.Entity):
    """
    A player.

    """
    BCRYPT_ROUNDS = 11

    name = Required(str, 40, unique=True)
    password_hash = Optional(str, 200)
    email = Optional(str, 200)

    date_joined = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    last_played = Optional(datetime)

    rounds_solved = Set('Round')
    submitted_reports = Set('Report')
    submitted_questions = Set(Question)

    def before_update(self):
        self.date_modified = datetime.now()

    def has_password(self):
        return bool(self.password_hash)

    def set_password(self, password):
        self.password_hash = bcrypt_sha256.encrypt(password, rounds=self.BCRYPT_ROUNDS)

    def check_password(self, password):
        if not self.has_password():
            return True
        if password is None:
            return False
        return bcrypt_sha256.verify(password, self.password_hash)


class Round(db.Entity):
    """
    A single round with a single question.

    """
    question = Required(Question)
    start_time = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    solved = Required(bool, default=False)
    solver = Optional(Player)
    time_taken = Optional(float)
    points = Required(int, default=0)

    @classmethod
    def new(cls, round_start):
        """
        Select a question and start a new round.

        """
        try:
            question = select(
                q for q in Question if q.active and (q.last_played is None or q.last_played < round_start)
            ).random(1)[0]
        except IndexError:
            question = select(
                q for q in Question if q.active
            ).order_by(Question.times_played).random(1)[0]
        return cls(question=question)

    @db_session
    def solved_by(self, player):
        self.solved = True
        self.solver = player
        self.time_taken = datetime.now().timestamp() - self.start_time.timestamp()

    @db_session
    def end_round(self):
        """
        Update the question statistics after a round.

        """
        self.question.set(
            last_played=datetime.now(),
            times_played=self.question.times_played + 1
        )
        if self.solved:
            self.question.set(
                times_solved=self.question.times_solved + 1
            )


class Report(db.Entity):
    """
    A report for a question.

    """
    question = Required(Question)
    player = Required(Player)
    text = Required(str)
    created = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    done = Required(bool, default=False)
