

default:
	@echo "Running gunicorn"
	gunicorn -b :8080 -k flask_sockets.worker app:app

deps: public/reconnecting-websocket.min.js
	@echo 'Fetched dependencies'

public/reconnecting-websocket.min.js:
	wget -O public/reconnecting-websocket.min.js https://raw.github.com/joewalnes/reconnecting-websocket/master/reconnecting-websocket.min.js
