import os
from datetime import datetime

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
    def answers(self):
        """Answers normalized to lower case."""
        return self.answer.lower().split('|')

    @property
    def primary_answer(self):
        return self.answer.split('|')[0]

    @property
    def category_names(self):
        return [c.name for c in self.categories.order_by(Category.name)]

    @property
    def solve_percentage(self):
        if self.times_played == 0:
            return 0
        return self.times_solved / self.times_played

    def check_answer(self, answer):
        return answer.lower() in self.answers


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

    def set_password(self, password):
        self.password_hash = bcrypt_sha256.encrypt(password, rounds=self.BCRYPT_ROUNDS)

    def check_password(self, password):
        if not self.password:
            return True
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

    def check_answer(self, player, answer):
        if self.question.check_answer(answer):
            self.solved = True
            self.solver = player
            self.time_taken = datetime.now() - self.start_time
            return True
        return False

    def end_round(self):
        """
        Update the question statistics after a round.

        """
        self.question.last_played = datetime.now()
        self.question.times_played += 1
        if self.solved:
            self.question.times_solved += 1


class Report(db.Entity):
    """
    A report for a question.

    """
    question = Required(Question)
    player = Required(Player)
    text = Required(str)
    created = Required(datetime, sql_default='CURRENT_TIMESTAMP')
    done = Required(bool, default=False)
