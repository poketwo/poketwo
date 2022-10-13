import os
import re
from collections import namedtuple
from urllib.parse import quote_plus

import discord
import discord.gateway
import discord.http
import yarl

import bot

Config = namedtuple(
    "Config",
    [
        "DATABASE_URI",
        "DATABASE_NAME",
        "BOT_TOKEN",
        "REDIS_CONF",
        "DBL_TOKEN",
        "SERVER_URL",
        "EXT_SERVER_URL",
        "ASSETS_BASE_URL",
    ],
)


def patch_with_gateway(env_gateway):
    class ProductionHTTPClient(discord.http.HTTPClient):
        async def get_gateway(self, **_):
            return f"{env_gateway}?encoding=json&v=9"

        async def get_bot_gateway(self, **_):
            try:
                data = await self.request(discord.http.Route("GET", "/gateway/bot"))
            except discord.HTTPException as exc:
                raise discord.GatewayNotFound() from exc
            return data["shards"], f"{env_gateway}?encoding=json&v=9"

    class ProductionDiscordWebSocket(discord.gateway.DiscordWebSocket):
        DEFAULT_GATEWAY = yarl.URL(env_gateway)

        def is_ratelimited(self):
            return False

    class ProductionBot(bot.ClusterBot):
        async def before_identify_hook(self, shard_id, *, initial):
            pass

        def is_ws_ratelimited(self):
            return False

    class ProductionReconnectWebSocket(Exception):
        def __init__(self, shard_id, *, resume=False):
            self.shard_id = shard_id
            self.resume = False
            self.op = "IDENTIFY"

    discord.http.HTTPClient.get_gateway = ProductionHTTPClient.get_gateway
    discord.http.HTTPClient.get_bot_gateway = ProductionHTTPClient.get_bot_gateway
    discord.gateway.DiscordWebSocket.DEFAULT_GATEWAY = ProductionDiscordWebSocket.DEFAULT_GATEWAY
    discord.gateway.DiscordWebSocket.is_ratelimited = ProductionDiscordWebSocket.is_ratelimited
    discord.gateway.ReconnectWebSocket.__init__ = ProductionReconnectWebSocket.__init__
    bot.ClusterBot = ProductionBot


if __name__ == "__main__":
    uri = os.getenv("DATABASE_URI")

    if uri is None:
        uri = "mongodb://{}:{}@{}".format(
            quote_plus(os.environ["DATABASE_USERNAME"]),
            quote_plus(os.environ["DATABASE_PASSWORD"]),
            os.environ["DATABASE_HOST"],
        )

    if os.getenv("API_BASE") is not None:
        discord.http.Route.BASE = os.getenv("API_BASE")

    if os.getenv("API_GATEWAY") is not None:
        patch_with_gateway(os.getenv("API_GATEWAY"))

    config = Config(
        DATABASE_URI=uri,
        DATABASE_NAME=os.environ["DATABASE_NAME"],
        BOT_TOKEN=os.environ["BOT_TOKEN"],
        REDIS_CONF={
            "address": os.environ["REDIS_URI"],
            "password": os.getenv("REDIS_PASSWORD"),
        },
        DBL_TOKEN=os.getenv("DBL_TOKEN"),
        SERVER_URL=os.environ["SERVER_URL"],
        EXT_SERVER_URL=os.getenv("EXT_SERVER_URL", os.environ["SERVER_URL"]),
        ASSETS_BASE_URL=os.getenv("ASSETS_BASE_URL"),
    )

    num_shards = int(os.getenv("NUM_SHARDS", 1))
    num_clusters = int(os.getenv("NUM_CLUSTERS", 1))
    cluster_name = os.getenv("CLUSTER_NAME", str(os.getenv("CLUSTER_IDX", 0)))
    cluster_idx = int(re.search(r"\d+", cluster_name).group(0))

    shard_ids = list(range(cluster_idx, num_shards, num_clusters))

    intents = discord.Intents.default()

    bot.ClusterBot(
        token=config.BOT_TOKEN,
        shard_ids=shard_ids,
        shard_count=num_shards,
        cluster_name=str(cluster_idx),
        cluster_idx=cluster_idx,
        case_insensitive=True,
        member_cache_flags=discord.MemberCacheFlags.none(),
        allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        intents=intents,
        config=config,
    )
