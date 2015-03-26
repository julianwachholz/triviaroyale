trivia.ju.io
============

An online game of trivia questions using websockets and python built on top of
its new asyncio feature with the help of
[aaugustin/websockets](https://github.com/aaugustin/websockets).

Database queries are performed using [PonyORM](http://ponyorm.com/).

You can play it right now on https://trivia.ju.io/


Running it yourself
-------------------

Map the `public` directory to a web-accessible folder for your web server.

Create a virtualenv with at least Python 3.4.

Then, you should be able to run the `app.py` file directly. See its source
for configuration options using environment variables.

Current default and fixed values:

- Using a local PostgreSQL database `trivia`
- Websockets listening on `localhost:8765` or `$LISTEN_IP` and `$LISTEN_PORT`
- If you want SSL, specify the `CERT_FILE` and `CERT_KEY` variables.

The database tables will be created automatically, but we currently have
no example questions for you (coming soon I guess).
Run the `app.py` in the admin folder to get a Flask instance with a very
simple and unprotected administrative interface.


Contributions
-------------

Contributions are always welcome! Please try to match the current
style but feel free to clean up messy things along the way. :)


TODO
----

- Submit new question
- Report question


License
-------

`trivia.ju.io` is licensed under BSD.
See `LICENSE` file for further information.
