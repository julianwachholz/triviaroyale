import os
import re
import time
import math
from datetime import datetime, timedelta

from pony.orm import *
from passlib.hash import bcrypt_sha256


db = Database()
sql_debug(bool(os.environ.get('DEBUG', False)))


class Category(db.Entity):
    """
    Questions should have at least one category.

    """
    name = Required(str, 40, unique=True)
    questions = Set('Question')


class Question(db.Entity):
    """
    Question objects.

    Multiple answers are separated using "|"

    """
    GET_RANDOM_SQL = """
        SELECT * FROM question
        WHERE active = true AND last_played < $round_start
        ORDER BY RANDOM() * (times_solved / (SELECT SUM(times_solved) FROM question)::float)
        LIMIT 100
    """
    BASE_POINTS = 500
    MIN_PLAYED_ROUNDS = 3
    STREAK_MODIFIER = 1.06

    active = Required(bool, default=False)

    question = Required(str, 200)
    media_url = Optional(str, 500)
    answer = Required(str, 200)

    categories = Set(Category)
    additional_info = Optional(str)

    times_played = Required(int, default=0)
    times_solved = Required(int, default=0)

    date_added = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    date_modified = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    last_played = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    rounds = Set('Round')
    reports = Set('Report')
    player = Optional('Player')

    @property
    def primary_answer(self):
        return self.answer.split('|')[0]

    @property
    def answer_re(self):
        if not hasattr(self, '_answer_re'):
            answers = map(lambda a: re.escape(a), self.answer.split('|'))
            pattern = r'\b{}\b'.format('|'.join(answers))
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

    def calculate_points(self, time_percentage, hints=0, streak=1):
        """
        Calculate how many points answering this question got someone.

        Here be dragons and crude math, mostly bad math though.

        """
        if self.times_played < self.MIN_PLAYED_ROUNDS:
            difficulty_factor = 1
        else:
            difficulty_factor = 0.5
            difficulty_factor += 1 / math.log10(max(self.solve_percentage, 1.1))  # prevent division by zero
        base_points = self.BASE_POINTS * difficulty_factor
        base_points *= self.STREAK_MODIFIER ** (streak - 1)
        return int((base_points * (1 - time_percentage)) / (hints + 1))


class Player(db.Entity):
    """
    A player.

    """
    BCRYPT_ROUNDS = 11

    name = Required(str, 40, unique=True)
    password_hash = Optional(str, 200)
    email = Optional(str, 200)

    date_joined = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    last_played = Required(datetime, sql_default='CURRENT_TIMESTAMP')

    rounds_solved = Set('Round')
    submitted_reports = Set('Report')
    submitted_questions = Set(Question)

    def logged_in(self):
        self.last_played = datetime.now()

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
        question = Question.select_by_sql(Question.GET_RANDOM_SQL)[0]
        return cls(question=question)

    @db_session
    def solved_by(self, player, total_time, hints=0, streak=1):
        self.solved = True
        self.solver = player
        self.time_taken = datetime.now().timestamp() - self.start_time.timestamp()
        self.points = self.question.calculate_points(
            self.time_taken / total_time, hints, streak)

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
