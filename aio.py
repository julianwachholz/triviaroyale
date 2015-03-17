#!/usr/bin/env python

import asyncio
import logging
import websockets


logger = logging.getLogger('websockets.server')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

players = set()


@asyncio.coroutine
def handler(ws, path):
    players.add(ws)
    while True:
        message = yield from ws.recv()
        if message is None:
            players.remove(ws)
            break

        print("< {}: {}".format(ws, message))
        asyncio.async(broadcast(message))


@asyncio.coroutine
def broadcast(message):
    for ws in players:
        if ws.open:
            yield from ws.send(message)
            print("> {}: {}".format(ws, message))

server = websockets.serve(handler, 'localhost', 8765)

loop = asyncio.get_event_loop()
loop.run_until_complete(server)
loop.run_forever()
