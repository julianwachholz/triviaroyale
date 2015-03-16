
FOUNDATION=5.5.1

default:
	@echo "Running admin app"
	python app.py

deps: static/css/foundation.min.css

static/css/foundation.min.css:
	wget -O foundation.zip http://foundation.zurb.com/cdn/releases/foundation-$(FOUNDATION).zip
	unzip -d static foundation.zip
	rm -rf static/img static/index.html static/robots.txt static/humans.txt
	rm foundation.zip

clean:
	rm -rf static/css static/js
