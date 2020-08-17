import asyncio
import json
import signal

import websockets
from aioconsole import ainput

CLIENTS = {}


async def dispatch(data):
    for cluster_name, client in CLIENTS.items():
        await client.send(data)
        print(f"> Cluster[{cluster_name}]")


async def serve(ws, path):
    cluster_name = await ws.recv()
    if cluster_name in CLIENTS:
        print(f"! Cluster[{cluster_name}] attempted reconnection")
        await ws.close(4029, "already connected")
        return
    CLIENTS[cluster_name] = ws
    try:
        await ws.send(b'{"status": "ok"}')
        print(f"$ Cluster[{cluster_name}] connected successfully")
        async for msg in ws:
            print(f"< Cluster[{cluster_name}]: {msg}")
            await dispatch(msg)
    finally:
        CLIENTS.pop(cluster_name)
        print(f"$ Cluster[{cluster_name}] disconnected")


async def console():
    while True:
        command = await ainput("$ ")
        ret = {"command": command}
        await dispatch(json.dumps(ret))


signal.signal(signal.SIGINT, signal.SIG_DFL)
signal.signal(signal.SIGTERM, signal.SIG_DFL)

server = websockets.serve(serve, "localhost", 42069)
loop = asyncio.get_event_loop()
loop.create_task(console())
loop.run_until_complete(server)

loop.run_forever()
