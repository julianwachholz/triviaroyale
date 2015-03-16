import asyncio


@asyncio.coroutine
def player():
    i = 1
    while i < 10:
        yield from asyncio.sleep(1.0)
        print("player say")
        print(loop.time())
        i += 1


@asyncio.coroutine
def game():
    print("game start")
    i = 1
    while i <= 5:
        yield from asyncio.sleep(2.0)
        print("game progress: {}".format(i))
        print(loop.time())
        i += 1
    print("game stop")
    loop.stop()

loop = asyncio.get_event_loop()
asyncio.async(game())
asyncio.async(player())

loop.run_forever()

print("exited")

loop.close()
