

default:
	@echo "Running gunicorn"
	gunicorn -b :8080 -k flask_sockets.worker app:app

deps: static/reconnecting-websocket.min.js
	@echo 'Fetched dependencies'

static/reconnecting-websocket.min.js:
	wget -O static/reconnecting-websocket.min.js https://raw.github.com/joewalnes/reconnecting-websocket/master/reconnecting-websocket.min.js
