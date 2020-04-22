#!/usr/bin/env python

import asyncio
import json
import logging
import os
import ssl

import websockets

from trivia.chat import GameController
from trivia.game import TriviaGame
from trivia.models import db

logging.basicConfig(
    format="%(asctime)s %(levelname)-7s %(module)+7s: %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)

game = GameController()

MAX_MSG_SIZE = 2 ** 10  # 1kb


async def game_handle(ws, data):
    keys = data.keys()

    if "ping" in keys and ws.open:
        asyncio.ensure_future(send(ws, {"pong": data.get("ping")}))

    if "command" in keys:
        game.command(ws, data.get("command"), data.get("args", None))

    if "text" in keys:
        game.chat(ws, data.get("text"))


async def handler(ws, path):
    game.join(ws)
    try:
        while True:
            try:
                message = await ws.recv()
            except websockets.exceptions.ConnectionClosed:
                break
            if len(message) > MAX_MSG_SIZE:
                logger.warn("Discarding message: Too long: {}".format(len(message)))
                continue
            try:
                data = json.loads(message)
            except ValueError:
                logger.warn(
                    "Discarding message: Invalid format: {}".format(message[:100])
                )
                continue
            asyncio.ensure_future(game_handle(ws, data))

            if "ping" not in data:
                await asyncio.sleep(0.25)  # message throttling
    finally:
        game.leave(ws)


async def send(ws, message):
    message = json.dumps(message)
    await ws.send(message)


async def broadcast(message):
    message = json.dumps(message)
    for ws in game.clients:
        await ws.send(message)


if __name__ == "__main__":
    listen_ip = os.environ.get("LISTEN_IP", "localhost")
    listen_port = int(os.environ.get("LISTEN_PORT", 8180))

    if "CERT_FILE" in os.environ and "CERT_KEY" in os.environ:
        secure = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        secure.load_cert_chain(os.environ["CERT_FILE"], os.environ["CERT_KEY"])
    else:
        secure = None

    db.bind(
        provider="postgres",
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS", ""),
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "trivia"),
    )
    db.generate_mapping(create_tables=True)

    server = websockets.serve(handler, listen_ip, listen_port, ssl=secure)

    trivia = TriviaGame(broadcast, send)
    game.trivia = trivia
    game.send = send
    game.broadcast = broadcast

    loop = asyncio.get_event_loop()
    loop.run_until_complete(server)
    loop.run_until_complete(trivia.run())
    loop.run_forever()
