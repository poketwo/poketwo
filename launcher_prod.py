import os
import re
from collections import namedtuple
from urllib.parse import quote_plus

import discord
import discord.gateway

import bot


def patch_with_gateway(env_gateway):
    class ProductionDiscordWebSocket(discord.gateway.DiscordWebSocket):
        def is_ratelimited(self):
            return False

        @classmethod
        async def from_client(
            cls, client, *, initial=False, gateway=None, shard_id=None, session=None, sequence=None, resume=False
        ):
            return await super().from_client(
                client,
                initial=initial,
                gateway=env_gateway,
                shard_id=shard_id,
                session=session,
                sequence=sequence,
                resume=resume,
            )

    class ProductionBot(bot.ClusterBot):
        async def before_identify_hook(self, shard_id, *, initial):
            pass

        def is_ws_ratelimited(self):
            return False

    discord.gateway.DiscordWebSocket = ProductionDiscordWebSocket
    bot.ClusterBot = ProductionBot


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
    ],
)

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
    )

    num_shards = int(os.getenv("NUM_SHARDS", 1))
    num_clusters = int(os.getenv("NUM_CLUSTERS", 1))
    cluster_name = os.getenv("CLUSTER_NAME", str(os.getenv("CLUSTER_IDX", 0)))
    cluster_idx = int(re.search(r"\d+", cluster_name).group(0))

    shard_ids = list(range(cluster_idx, num_shards, num_clusters))

    bot.ClusterBot(
        token=config.BOT_TOKEN,
        shard_ids=shard_ids,
        shard_count=num_shards,
        cluster_name=str(cluster_idx),
        cluster_idx=cluster_idx,
        case_insensitive=True,
        member_cache_flags=discord.MemberCacheFlags.none(),
        allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        intents=discord.Intents.default(),
        config=config,
    )
