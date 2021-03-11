import os
from collections import namedtuple

import discord

from bot import ClusterBot

Config = namedtuple(
    "Config",
    [
        "DATABASE_URI",
        "DATABASE_NAME",
        "BOT_TOKEN",
        "SECRET_KEY",
        "REDIS_CONF",
        "DBL_TOKEN",
    ],
)

if __name__ == "__main__":
    config = Config(
        DATABASE_URI=os.environ["DATABASE_URI"],
        DATABASE_NAME=os.environ["DATABASE_NAME"],
        BOT_TOKEN=os.environ["BOT_TOKEN"],
        SECRET_KEY=os.environ["SECRET_KEY"],
        REDIS_CONF={
            "address": os.environ["REDIS_URI"],
            "password": os.getenv("REDIS_PASSWORD"),
        },
        DBL_TOKEN=os.getenv("DBL_TOKEN"),
    )

    num_shards = os.getenv("NUM_SHARDS", 1)
    num_clusters = os.getenv("NUM_CLUSTERS", 1)
    cluster_idx = os.getenv("CLUSTER_IDX", 0)

    shard_ids = list(range(cluster_idx, num_shards, num_clusters))

    ClusterBot(
        token=config.BOT_TOKEN,
        shard_ids=shard_ids,
        shard_count=num_shards,
        cluster_name=str(cluster_idx),
        cluster_idx=cluster_idx,
        case_insensitive=True,
        fetch_offline_members=False,
        allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        intents=discord.Intents.default(),
        config=config,
    )
