import asyncio
import logging
import multiprocessing
import os
import signal
import time

import config
import discord
import requests

from bot import ClusterBot

log = logging.getLogger("Cluster#Launcher")
log.setLevel(logging.INFO)
hdlr = logging.StreamHandler()
hdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
fhdlr = logging.FileHandler("logs/launcher.log", encoding="utf-8")
fhdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
log.handlers = [hdlr, fhdlr]

CLUSTER_NAMES = (
    "Arbok",
    "Bulbasaur",
    "Charmander",
    "Diglett",
    "Eevee",
    "Fennekin",
    "Gengar",
    "Houndoom",
    "Inkay",
    "Jigglypuff",
    "Koffing",
    "Lickitung",
    "Machamp",
    "Nidoran",
    "Omanyte",
    "Pikachu",
    "Quagsire",
    "Ralts",
    "Snorlax",
    "Togepi",
    "Umbreon",
    "Vanillite",
    "Wooloo",
    "Xatu",
    "Yanma",
    "Zorua",
)

NAMES = iter(CLUSTER_NAMES)

intents = discord.Intents.default()


class Launcher:
    def __init__(self, loop):
        log.info("Hello, world!")
        self.cluster_queue = []
        self.clusters = []

        self.fut = None
        self.loop = loop
        self.alive = True

        self.keep_alive = None
        self.init = time.perf_counter()

    def get_shard_count(self):
        data = requests.get(
            "https://discordapp.com/api/v7/gateway/bot",
            headers={
                "Authorization": "Bot " + config.BOT_TOKEN,
                "User-Agent": "DiscordBot (https://github.com/Rapptz/discord.py 1.4.1) Python/3.7 aiohttp/3.6.1",
            },
        )
        data.raise_for_status()
        content = data.json()
        log.info(
            f"Successfully got shard count of {content['shards']} ({data.status_code}, {data.reason})"
        )
        # return 16
        return content["shards"]

    def start(self):
        self.fut = asyncio.ensure_future(self.startup(), loop=self.loop)

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.shutdown())
        finally:
            self.cleanup()

    def cleanup(self):
        self.loop.stop()
        self.loop.close()

    def task_complete(self, task):
        if task.exception():
            task.print_stack()
            self.keep_alive = self.loop.create_task(self.rebooter())
            self.keep_alive.add_done_callback(self.task_complete)

    async def startup(self):
        shards = list(range(self.get_shard_count()))
        size = [shards[x : x + 4] for x in range(0, len(shards), 4)]
        log.info(f"Preparing {len(size)} clusters")
        for shard_ids in size:
            self.cluster_queue.append(Cluster(self, next(NAMES), shard_ids, len(shards)))

        await self.start_cluster()
        self.keep_alive = self.loop.create_task(self.rebooter())
        self.keep_alive.add_done_callback(self.task_complete)
        log.info(f"Startup completed in {time.perf_counter()-self.init}s")

    async def shutdown(self):
        log.info("Shutting down clusters")
        self.alive = False
        if self.keep_alive:
            self.keep_alive.cancel()
        for cluster in self.clusters:
            cluster.stop()
        self.cleanup()

    async def rebooter(self):
        while self.alive:
            if not self.clusters:
                log.warning("All clusters appear to be dead")
                asyncio.ensure_future(self.shutdown())
            for cluster in self.clusters:
                if not cluster.process.is_alive():
                    log.info(f"Cluster#{cluster.name} exited with code {cluster.process.exitcode}")
                    log.info(f"Restarting cluster#{cluster.name}")
                    await cluster.start()
            await asyncio.sleep(5)

    async def start_cluster(self):
        for cluster in self.cluster_queue:
            self.clusters.append(cluster)
            log.info(f"Starting Cluster#{cluster.name}")
            self.loop.create_task(cluster.start())
            await asyncio.sleep(0.5)


class Cluster:
    def __init__(self, launcher, name, shard_ids, max_shards):
        self.launcher = launcher
        self.process = None
        self.kwargs = dict(
            token=config.BOT_TOKEN,
            shard_ids=shard_ids,
            shard_count=max_shards,
            cluster_name=name,
            cluster_idx=CLUSTER_NAMES.index(name),
            case_insensitive=True,
            fetch_offline_members=False,
            member_cache_flags=discord.MemberCacheFlags.none(),
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
            intents=intents,
        )
        self.name = name
        self.log = logging.getLogger(f"Cluster#{name}")
        self.log.setLevel(logging.DEBUG)
        hdlr = logging.StreamHandler()
        hdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
        fhdlr = logging.FileHandler("logs/launcher.log", encoding="utf-8")
        fhdlr.setFormatter(logging.Formatter("[%(asctime)s %(name)s/%(levelname)s] %(message)s"))
        self.log.handlers = [hdlr, fhdlr]
        self.log.info(f"Initialized with shard ids {shard_ids}, total shards {max_shards}")

    def wait_close(self):
        return self.process.join()

    async def start(self, *, force=False):
        if self.process and self.process.is_alive():
            if not force:
                self.log.warning(
                    "Start called with already running cluster, pass `force=True` to override"
                )
                return
            self.log.info("Terminating existing process")
            self.process.terminate()
            self.process.close()

        self.process = multiprocessing.Process(target=ClusterBot, kwargs=self.kwargs, daemon=True)
        self.process.start()
        self.log.info(f"Process started with PID {self.process.pid}")

        return True

    def stop(self, sign=signal.SIGINT):
        self.log.info(f"Shutting down with signal {sign!r}")
        try:
            os.kill(self.process.pid, sign)
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    Launcher(loop).start()
