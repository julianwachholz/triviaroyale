# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from wtforms import Form, TextField, BooleanField, SelectMultipleField, \
    validators, widgets


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class CategoryForm(Form):
    name = TextField('Name', [validators.Length(min=2, max=25)])


class QuestionForm(Form):
    question = TextField('Question', [validators.Length(min=10, max=140)])
    answer = TextField('Answer', [validators.Length(min=2, max=40)])
    active = BooleanField('Is active?')

    category_list = MultiCheckboxField('Categories', [validators.DataRequired()], coerce=int)
