# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division

import os
import math
import logging

from flask import Flask, flash, request, redirect, url_for, render_template

from trivia.models import *

from forms import CategoryForm, QuestionForm


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'secret!'


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/category/')
@db_session
def category_list():
    page = int(request.args.get('p', 1))
    if page < 1:
        page = 1
    pagesize = 10

    categories = select((c.id, c.name, count(c.questions)) for c in Category)
    category_count = count(c for c in Category)

    return render_template(
        'category/list.html',
        page=page,
        pages=int(math.ceil(category_count / pagesize)),
        category_list=categories.page(page, pagesize),
        category_count=category_count,
    )


@app.route('/category/create/', methods=['GET', 'POST'])
@app.route('/category/<int:id>/', methods=['GET', 'POST'])
@db_session
def category_form(id=None):
    category = None
    if id:
        category = Category[id]
    form = CategoryForm(request.form, category)

    if request.method == 'POST' and form.validate():
        if category:
            category.set(name=form.name.data)
            flash('Category updated!', 'success')
        else:
            Category(name=form.name.data)
            flash('Category created!', 'success')
        return redirect(url_for('category_list'))

    return render_template(
        'category/form.html',
        category=category,
        form=form,
    )


@app.route('/category/<int:id>/delete/', methods=['GET', 'POST'])
@db_session
def category_delete(id):
    category = Category[id]

    if request.method == 'POST':
        category.delete()
        flash('Category deleted!', 'info')
        return redirect(url_for('category_list'))

    return render_template(
        'category/confirm_delete.html',
        category=category,
    )


@app.route('/question/')
@db_session
def question_list():
    context = {}
    questions = select(q for q in Question)

    if 'c' in request.args:
        try:
            category = Category[int(request.args.get('c'))]
            context['filter'] = 'in {}'.format(category.name)
            questions = questions.filter(lambda q: category in q.categories)
        except ObjectNotFound:
            pass

    question_count = count(questions)
    questions = questions.order_by(Question.id)

    pagesize = 10
    page = int(request.args.get('p', 1))
    pages = int(math.ceil(question_count / pagesize))
    if 1 > page > pages:
        page = 1

    context['page'] = page
    context['pages'] = pages

    return render_template(
        'question/list.html',
        question_list=questions.page(page, pagesize),
        question_count=question_count,
        **context
    )


@app.route('/question/create/', methods=['GET', 'POST'])
@app.route('/question/<int:id>/', methods=['GET', 'POST'])
@db_session
def question_form(id=None):
    question = None
    if id:
        question = Question[id]

    form_kwargs = {
        'obj': question,
    }

    if question:
        form_kwargs['category_list'] = [c.id for c in question.categories]

    form = QuestionForm(request.form, **form_kwargs)
    form.category_list.choices = select((c.id, c.name) for c in Category)[:]

    if request.method == 'POST' and form.validate():
        data = {
            'question': form.question.data,
            'answer': form.answer.data,
            'active': form.active.data,
            'categories': [Category[id] for id in form.category_list.data]
        }

        if question:
            question.set(**data)
            flash('Question updated!', 'success')
        else:
            question = Question(**data)
            flash('Question created!', 'success')

        return redirect(url_for('question_list'))

    return render_template(
        'question/form.html',
        question=question,
        form=form,
    )


@app.route('/question/<int:id>/delete/', methods=['GET', 'POST'])
@db_session
def question_delete(id):
    question = Question[id]

    if request.method == 'POST':
        question.delete()
        flash('Question deleted!', 'info')
        return redirect(url_for('question_list'))

    return render_template(
        'question/confirm_delete.html',
        question=question,
    )


if __name__ == '__main__':
    db.bind('postgres', database='trivia')
    db.generate_mapping(create_tables=True)
    app.run(debug=True, port=8081)
