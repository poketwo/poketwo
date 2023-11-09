from __future__ import annotations

import math
import random
import textwrap
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple, Union

import discord
from discord.ext import commands, tasks
from discord.utils import get

from cogs import mongo
from cogs.mongo import Member, Pokemon
from data.models import Species
from helpers import checks
from helpers.constants import HALLOWEEN_EVENT_COLOR
from helpers.context import PoketwoContext
from helpers.converters import FetchUserConverter, ItemAndQuantityConverter
from helpers.pagination import ContinuablePages, FunctionPageSource
from helpers.utils import FlavorString, make_slider, unwind

if TYPE_CHECKING:
    from bot import ClusterBot


STORY_URL = "https://gist.github.com/WitherredAway/5eadc92aa630df36abeefa8a5f2dc200"
HALLOWEEN_PREFIX = "halloween_2023_"
COMPLETION_EMBED_COLOR = 0xC0F4CD

RUINED_GOLURK_ID = 50139
HERO_GOLURK_ID = 50140


NOTHING = "Nothing to show yet...\n"
SATCHEL_DROP_CHANCE = 0.25
SATCHEL_CHANCES = {
    "pc": 0.25,
    "sigil": 0.25,
    "non-event": 0.409,
    "non-event-shiny": 0.001,
    "event-sage": 0.04,
    "nothing": 0.05,
}
SATCHEL_REWARD_AMOUNTS = {
    "pc": range(100, 1000),
    "sigil": [1],
    "non-event": [1],
    "non-event-shiny": [1],
    "event-sage": [1],
    "nothing": [1],
}

SATCHEL_REWARDS = [*SATCHEL_CHANCES.keys()]
SATCHEL_WEIGHTS = [*SATCHEL_CHANCES.values()]

SATCHEL_IDS = unwind(
    {
        ("flame", "flames", "satchel of flame", "satchel of flames"): "satchel_flames",
        ("shadow", "shadows", "satchel of shadow", "satchel of shadows"): "satchel_shadows",
        ("foliage", "satchel of foliage"): "satchel_foliage",
        ("snaring", "satchel of snaring"): "satchel_snaring",
    },
    include_values=True,
)

SATCHEL_TYPES = unwind(
    {
        ("Fire", "Electric", "Dragon", "Flying"): "satchel_flames",
        ("Dark", "Ghost", "Ground", "Rock"): "satchel_shadows",
        ("Grass", "Bug", "Steel", "Water", "Poison"): "satchel_foliage",
        ("Psychic", "Fairy", "Ice", "Fighting", "Normal"): "satchel_snaring",
    },
)

SATCHEL_SIGILS = {
    "satchel_flames": "sigil_flames",
    "satchel_shadows": "sigil_shadows",
    "satchel_foliage": "sigil_foliage",
    "satchel_snaring": "sigil_snaring",
}
SIGIL_SATCHELS = {v: k for k, v in SATCHEL_SIGILS.items()}

SIGIL_IDS = unwind(
    {
        ("flame", "flames", "sigil of flame", "sigil of flames"): "sigil_flames",
        ("shadow", "shadows", "sigil of shadow", "sigil of shadows"): "sigil_shadows",
        ("foliage", "sigil of foliage"): "sigil_foliage",
        ("snaring", "sigil of snaring"): "sigil_snaring",
    },
    include_values=True,
)

BADGE_NAME = "halloween_2023"
BADGE_REQ_PERCENT = 21e-6


class FlavorStrings:
    """Holds various flavor strings"""

    satchel_flames = FlavorString("Satchel of Flames", "<:satchel_flames:1163537490171408424>", "Satchels of Flames")
    satchel_shadows = FlavorString(
        "Satchel of Shadows", "<:satchel_shadows:1163537497658237040>", "Satchels of Shadows"
    )
    satchel_foliage = FlavorString(
        "Satchel of Foliage", "<:satchel_foliage:1163537505098924173>", "Satchels of Foliage"
    )
    satchel_snaring = FlavorString(
        "Satchel of Snaring", "<:satchel_snaring:1163537511864344597>", "Satchels of Snaring"
    )

    sigil_flames = FlavorString("Sigil of Flames", "<:sigil_flames:1164314714218700852>", "Sigils of Flames")
    sigil_shadows = FlavorString("Sigil of Shadows", "<:sigil_shadows:1164314698817228911>", "Sigils of Shadows")
    sigil_foliage = FlavorString("Sigil of Foliage", "<:sigil_foliage:1164314708883554354>", "Sigils of Foliage")
    sigil_snaring = FlavorString("Sigil of Snaring", "<:sigil_snaring:1164314691187781663>", "Sigils of Snaring")

    pokecoins = FlavorString("Pokécoins")


def valid_string(items: Iterable[str]):
    return ", ".join(set([getattr(FlavorStrings, sid).string for sid in items]))


# Command strings
CMD_HALLOWEEN = "`{0} halloween`"
CMD_OFFER = "`{0} halloween offer <sigil> <qty>`"
CMD_OPEN = "`{0} halloween open <satchel> <qty>`"
CMD_INVENTORY = "`{0} halloween inventory`"
CMD_MILESTONES = "`{0} halloween milestones`"


TIPS = ("You can see your contribution after the completion of each milestone.",)
SIGIL_TIPS = (
    "Sigils can be found in satchels, which can drop from wild catches!",
    "Offering the preferred sigil will contribute more than other sigils!",
    f"Offer sigils using {CMD_OFFER.format('@Pokétwo')}.",
)


MILESTONE_ID_PREFIX = f"{HALLOWEEN_PREFIX}milestone_"
MILESTONE_GOAL_ID_PREFIX = f"{HALLOWEEN_PREFIX}milestone_goal_"
CONTRIBUTION_ID_PREFIX = f"{MILESTONE_ID_PREFIX}contribution_"

ASSETS_ENDPOINT = "/assets/halloween_2023/{0}.png"


@dataclass
class Milestone:
    bot: ClusterBot
    id: str
    title: str
    text: str
    color: int
    quest: MilestoneQuest
    unlocks: str

    completion_text: Optional[str] = None
    completion_image_endpoint: Optional[str] = None

    @property
    def full_id(self):
        return f"{MILESTONE_ID_PREFIX}{self.id}"

    @property
    def contribution_id(self):
        return f"{CONTRIBUTION_ID_PREFIX}{self.id}"

    @property
    def goal_id(self):
        return f"{MILESTONE_GOAL_ID_PREFIX}{self.id}"

    @property
    def image_endpoint(self):
        return ASSETS_ENDPOINT.format(self.id)

    @property
    def unlock_text(self) -> str:
        # Build reward text
        unlocks = self.unlocks
        key, _id = unlocks.lower().split("_")
        match key:
            case "satchel":
                unlock_value = f"*{getattr(FlavorStrings, unlocks)}* drops"
            case "spawn":
                unlock_value = f"*{self.bot.data.species_by_number(int(_id))}* spawns"
        return unlock_value

    def get_goal_text(self, goal: int):
        # Determine progress requirement text
        match (event := self.quest.event).lower().split("_")[0]:
            case "sigil":  # If the milestone progresses with sigils
                action = "Offer"
                target = f"{getattr(FlavorStrings, event):s}"
            case "catch":  # If the milestone progresses with catches
                action = "Catch"
                target = "pokémon"

                condition = self.quest.condition
                if condition:
                    if species_id := condition.get("id"):
                        # Get species name from id in the milestone event
                        target = str(self.bot.data.species_by_number(species_id))

        return f"{action} {goal:,} *{target}*"

    async def get_progress(self) -> float:
        """Method to get the progress of the milestone."""

        counter = await self.bot.mongo.db.counter.find_one({"_id": self.full_id})
        return float(counter.get("next", 0) if counter is not None else 0)

    async def increment_progress(self, value: Union[float, int], *, user: Union[discord.User, discord.Member]):
        """Method to increment the progress of the milestone."""

        try:
            float(value)
        except ValueError:
            raise ValueError("progress must be an integer or float")

        milestone_data = await self.bot.mongo.db.counter.find_one_and_update(
            {"_id": self.full_id}, {"$inc": {"next": value}}, upsert=True
        )
        await self.bot.mongo.update_member(
            user,
            {"$inc": {self.contribution_id: value}},
        )
        return float((milestone_data.get("next", 0) if milestone_data is not None else 0) + value)

    async def is_complete(self):
        """Method to get whether the milestone is complete; if the progress of the milestone has reached its goal."""

        return await self.get_progress() >= await self.get_goal()

    async def get_goal(self) -> int:
        """Method to get the milestone's goal from the database"""

        default = self.quest.default_goal
        goal = await self.bot.mongo.db.counter.find_one({"_id": self.goal_id})
        if goal is None:
            await self.set_goal(default)
            return default
        counter = goal.get("next")
        if counter is None:
            await self.set_goal(default)
            return default
        return counter

    async def set_goal(self, goal: int):
        """Method to set the milestone's goal"""

        assert isinstance(goal, int), "goal must be an int"
        await self.bot.mongo.db.counter.update_one({"_id": self.goal_id}, {"$set": {"next": goal}}, upsert=True)


@dataclass
class MilestoneQuest:
    event: str
    default_goal: int
    condition: Optional[dict] = None


def trunc_percent(percent, dp: Optional[int] = 2) -> float:
    """Truncates a number to `dp` decimal points, without rounding"""
    return round(int(percent * 10**dp) / 10**dp, dp)


class HalloweenView(discord.ui.View):
    def __init__(self, ctx: PoketwoContext, *, all_complete: Optional[bool] = False):
        self.ctx = ctx
        self.halloween_cog: Halloween = self.ctx.bot.get_cog("Halloween")
        super().__init__(timeout=120)
        if all_complete:
            self.milestones.style = discord.ButtonStyle.green

    @discord.ui.button(label="Milestones", style=discord.ButtonStyle.blurple)
    async def milestones(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.halloween_cog.milestones)

    @discord.ui.button(label="Inventory", style=discord.ButtonStyle.blurple)
    async def inventory(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.ctx.invoke(self.halloween_cog.inventory)

    async def interaction_check(self, interaction):
        if interaction.user.id not in {
            self.ctx.bot.owner_id,
            self.ctx.author.id,
            *self.ctx.bot.owner_ids,
        }:
            await interaction.response.send_message("You can't use this!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)


class Halloween(commands.Cog):
    """Halloween event commands."""

    def __init__(self, bot):
        self.bot: ClusterBot = bot

    # async def cog_load(self):
    #     self.enable_spawns.start()

    # async def cog_unload(self):
    #     self.enable_spawns.stop()

    @cached_property
    def MILESTONES(self) -> Tuple[Milestone]:
        """List that holds pre-defined Milestone objects"""
        return (
            Milestone(
                bot=self.bot,
                id="searching_golurk",
                title="Searching for Golurk",
                text=(
                    "Barely maintaining its conscience, the Ruined Golurk has managed to escape deep into the woods and isolate itself"
                    " in order to avoid bringing harm to others. The sages have a plan to help, but they must first find it."
                    " Help the four sages search for the hurt Golurk by *catching pokémon*. Be wary though, as the Foul Beasts"
                    " still roam the land, looking for their next prey."
                ),
                color=0xF7D246,
                quest=MilestoneQuest(event="catch", default_goal=2000000),
                unlocks="satchel_flames",
            ),
            Milestone(
                bot=self.bot,
                id="helping_flames",
                title="Helping Sage of Flames",
                text=(
                    "The Sage of Flames uses its powers to locate the Ruined Golurk, and the Sinister Sages must all traverse the ruined forest"
                    " in pursuit. Foul Beasts pose greater threats as they approach the heart of the forest, where the once heroic Golurk lies in ruin."
                    f" Offer *{FlavorStrings.sigil_flames:s!e}* to help the Sage of Flames maintain its flow of magic that guides the Sages."
                ),
                color=0x4688AA,
                quest=MilestoneQuest(event="sigil_flames", default_goal=50000),
                unlocks="satchel_shadows",
            ),
            Milestone(
                bot=self.bot,
                id="helping_shadows",
                title="Helping Sage of Shadows",
                text=(
                    "As the Sinister Sages approach the injured Golurk, loud ominous hums seeping through the cracks imbued in its armor fill the forest."
                    " The Ruined Golurk viciously leaps at the sages, before being shackled by chains of pure darkness summoned by the Sage of Shadows."
                    f" But these chains cannot contain its eternal rage for long. Offer *{FlavorStrings.sigil_shadows:s!e}* to help strengthen these chains,"
                    " while the other sages put their plan into motion."
                ),
                color=0xA55CB5,
                quest=MilestoneQuest(event="sigil_shadows", default_goal=100000),
                unlocks="satchel_foliage",
            ),
            Milestone(
                bot=self.bot,
                id="helping_foliage",
                title="Helping Sage of Foliage",
                text=(
                    "The shadow chains cast by the Sage of Shadows and empowered by the sigils, hold the rampaging Golurk as it struggles to break free."
                    " The Sage of Foliage studies the anomaly within the Golurk's body, formulating the creation of a new seal that can contain this energy."
                    f" Offer *{FlavorStrings.sigil_foliage:s!e}* to enhance the materialization of the only thing capable of putting an end to the Golurk's fury."
                ),
                color=0x84B45F,
                quest=MilestoneQuest(event="sigil_foliage", default_goal=150000),
                unlocks="satchel_snaring",
            ),
            Milestone(
                bot=self.bot,
                id="helping_snaring",
                title="Helping Sage of Snaring",
                text=(
                    "The new seal, imbued with a crystal that negates the infernal energy within the Ruined Golurk, is ready to be placed,"
                    " when suddenly the cracks in its body grow wider, releasing more dormant power and enabling its escape."
                    " The Sage of Snaring quickly seizes the seal and pursues the now more potent yet fatigued Golurk into the forest."
                    f" Help the Sage of Snaring catch up to it by offering *{FlavorStrings.sigil_snaring:s!e}*."
                ),
                color=0xE7BE84,
                quest=MilestoneQuest(event="sigil_snaring", default_goal=175000),
                unlocks=f"spawn_{RUINED_GOLURK_ID}",
            ),
            Milestone(
                bot=self.bot,
                id="saving_golurk",
                title="Saving Golurk!",
                text=(
                    "The Sage of Snaring, through the power of the sigils, ensnares the fleeing Golurk. Its movement restricted"
                    " and having no option but to fight back, the Ruined Golurk kneels down, preparing to lunge at the sage with full might."
                    " Catch *Ruined Golurks* in the wild to further immobilize the Ruined Golurk, and give the sage an opening"
                    " to reseal the darkness seeping from within and restore what was once just a benevolent giant."
                ),
                completion_text=(
                    "The relentless battle between the Sage of Snaring and the Golurk carry on, exchanging attacks and sending shockwaves"
                    " through the desolate forest. Suddenly, familiar shadowy chains conjured by the Sage of Shadows rise once again and bind"
                    " the colossal foe in place, giving the Sage of Snaring the opening to smash the seal into the Golurk's chestpiece."
                    " A resounding roar fills the air as the Golurk's malevolence is sealed away, and the cracks in its body slowly begin to mend."
                    " The seal fuses with the Golurk, transforming it into an all-powerful form. Thus the Hero Golurk was born anew, gifted with"
                    " powers to be used for good, to atone for the harm it has unwittingly afflicted on others."
                ),
                completion_image_endpoint=ASSETS_ENDPOINT.format("complete"),
                color=0x13011C,
                quest=MilestoneQuest(
                    event="catch",
                    default_goal=30000,
                    condition={"id": RUINED_GOLURK_ID},
                ),
                unlocks=f"spawn_{HERO_GOLURK_ID}",
            ),
        )

    async def get_current_milestone(self) -> Union[Milestone, None]:
        """Method to get the milestone currently in progress."""

        for milestone in self.MILESTONES:
            if not await milestone.is_complete():
                break

        return milestone

    async def get_unlocked(self) -> List[str]:
        """Returns a list of all unlocked rewards' IDs"""

        return [m for m in self.MILESTONES if await m.is_complete()]

    # @tasks.loop(seconds=5)
    # async def enable_spawns(self):
    #     """Loop to enable the spawns that were unlocked from milestones."""

    #     for unlock, unlocked in [
    #         (m.unlocks, await m.is_complete()) for m in self.MILESTONES if m.unlocks.startswith("spawn")
    #     ]:
    #         key, _id = unlock.split("_")
    #         species = self.bot.data.species_by_number(int(_id))
    #         species.catchable = unlocked

    # @enable_spawns.before_loop
    # async def before_enable_spawns(self):
    #     await self.bot.wait_until_ready()

    async def satchel_unlocked(self, satchel: str) -> bool:
        """Returns if a satchel has been unlocked yet"""

        return satchel in (m.unlocks for m in await self.get_unlocked())

    def verify_condition(self, condition: Dict[str, Any], species: Species):
        if condition is not None:
            for k, v in condition.items():
                if k == "id" and species.id != v:
                    return False
        return True

    # @commands.Cog.listener("on_catch")
    # async def progress_catching_milestone(self, ctx: PoketwoContext, species: Species, idx: int):
    #     """on_catch event listener for progressing catching milestones"""

    #     milestone = await self.get_current_milestone()
    #     if await milestone.is_complete():
    #         return

    #     quest = milestone.quest
    #     if quest.event == "catch":
    #         condition = quest.condition
    #         if self.verify_condition(condition, species):
    #             await milestone.increment_progress(1, user=ctx.author)

    # @commands.Cog.listener(name="on_catch")
    # async def drop_satchel(self, ctx: PoketwoContext, species: Species, _id: int):
    #     if random.random() <= SATCHEL_DROP_CHANCE:
    #         types = [t for t in species.types if await self.satchel_unlocked(SATCHEL_TYPES[t])]
    #         if not types:
    #             return

    #         pokemon_type = random.choice(types)
    #         satchel = SATCHEL_TYPES[pokemon_type]

    #         await self.bot.mongo.update_member(ctx.author, {"$inc": {HALLOWEEN_PREFIX + satchel: 1}})
    #         await ctx.send(
    #             f"You found a {getattr(FlavorStrings, satchel)}! Use {CMD_HALLOWEEN.format(ctx.clean_prefix.strip())} for more info."
    #         )

    @cached_property
    def pools(self) -> Dict[str, List[Species]]:
        p = {
            "satchel_flames": [50138],
            "satchel_shadows": [50136],
            "satchel_foliage": [50135],
            "satchel_snaring": [50137],
            "non-event": self.bot.data.pokemon.keys(),
        }
        return {k: [self.bot.data.species_by_number(i) for i in v] for k, v in p.items()}

    async def make_pokemon(
        self, owner: discord.User | discord.Member, member: Member, *, species: Species, shiny_boost: Optional[int] = 1
    ):
        ivs = [mongo.random_iv() for _ in range(6)]
        shiny = member.determine_shiny(species, boost=shiny_boost)
        return {
            "owner_id": member.id,
            "owned_by": "user",
            "species_id": species.id,
            "level": min(max(int(random.normalvariate(20, 10)), 1), 50),
            "xp": 0,
            "nature": mongo.random_nature(),
            "iv_hp": ivs[0],
            "iv_atk": ivs[1],
            "iv_defn": ivs[2],
            "iv_satk": ivs[3],
            "iv_sdef": ivs[4],
            "iv_spd": ivs[5],
            "iv_total": sum(ivs),
            "shiny": shiny,
            "idx": await self.bot.mongo.fetch_next_idx(owner),
        }

    @checks.has_started()
    @commands.group(aliases=("event", "ev"), invoke_without_command=True, case_insensitive=True)
    async def halloween(self, ctx: PoketwoContext):
        """View halloween event main menu."""

        prefix = ctx.clean_prefix.strip()

        current_milestone = await self.get_current_milestone()
        all_complete = await current_milestone.is_complete()

        description = (
            (
                f"There is an [ancient story of a heroic Golurk]({STORY_URL}) who lost control"
                " of its power after its chest seal was torn off during a battle. Now, four Pokémon known as the Sinister Sages are on a quest"
                " to restore it using their unique abilities, all while dangerous and wicked Pokémon roam the woods in its absence."
                "\n\nAs the venture to recover the Ruined Golurk pursues, the four sages are faced with trials and tribulations and need your help!"
                " Join the sages and help them accomplish their mission by completing milestones as a community."
                " Each milestone unlocks what you need for the next, and you'll earn rewards along the way!"
            )
            if not all_complete
            else (
                f"[Once upon a time, there was a heroic Golurk]({STORY_URL}) who lost control of its power after its chest seal was torn off during a battle."
                " Now, with the help of the Pokétwo community, and after many battles and challenges, the Sinister Sages"
                " have saved the forest and the Golurk has transformed into an all-new heroic form!"
                "\n\nNo longer shall the forest be haunted"
                " by the once irrepressible force contained within the Golurk's body. Having regained its conscience, the Hero Golurk now lends its protection"
                " to those in need, warding off the Foul Beasts that once brought ruin upon the forest."
            )
        )
        embed = self.bot.Embed(
            title=f"Halloween 2023 - The Tale of the Ruined Golurk",
            description=description,
            color=COMPLETION_EMBED_COLOR if all_complete else HALLOWEEN_EVENT_COLOR,
        )

        embed.add_field(
            name="How it works",
            value=(
                f"This event brings with it {len(self.MILESTONES)} milestones that the entire Pokétwo community will collectively participate in!"
                " Each milestone progresses the story and unlocks new features and new special pokémon to unlock!"
            ),
            inline=False,
        )

        embed.add_field(
            name="Unlocked",
            value="\n".join((f"{i}. {m.unlock_text}" for i, m in enumerate(await self.get_unlocked(), 1))) or NOTHING,
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Use {CMD_MILESTONES.format(prefix)} to view milestones."
                f"\nUse {CMD_INVENTORY.format(prefix)} to view your satchels and sigils."
            )
        )

        view = HalloweenView(ctx, all_complete=all_complete)
        view.message = await ctx.send(embed=embed, view=view)

    @checks.has_started()
    @halloween.command(aliases=("milestone",))
    async def milestones(self, ctx: PoketwoContext):
        """View milestones"""

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_milestone = await self.get_current_milestone()
        all_complete = await current_milestone.is_complete()
        current_milestone_page = self.MILESTONES.index(current_milestone)

        milestones = self.MILESTONES[: current_milestone_page + 1]

        async def get_page(source, menu, pidx):
            milestone: Milestone = milestones[pidx]
            image_endpoint = milestone.image_endpoint

            progress = await milestone.get_progress()
            goal = await milestone.get_goal()
            complete = progress >= goal

            milestone_embed = self.bot.Embed(
                color=milestone.color,
                title=f"Community Milestone {pidx + 1}/{len(self.MILESTONES)} - {milestone.title}",
                description=milestone.text if not complete else f"~~{milestone.text}~~",
            )
            footer = []

            # Build Goal field value
            goal_value = [milestone.get_goal_text(goal)]

            # Make progress bar along with percentage truncated to 2 decimal points
            progress_percent = progress / goal * 100
            goal_value.append(f"{make_slider(self.bot, progress / goal)} `{trunc_percent(progress_percent)}%`")

            if complete:
                contribution = member[milestone.contribution_id]
                cont_int = int(contribution)
                goal_value.append(
                    f"**Your contribution**: `{cont_int if (cont_int - contribution) == 0 else contribution:,}/{goal:,}`"
                )
                footer.append("This milestone has been completed.")
            else:
                footer.append(
                    f"Tip: {random.choice(TIPS + SIGIL_TIPS if milestone.quest.event.startswith('sigil') else TIPS)}"
                )

            milestone_embed.add_field(name="Goal", value="\n".join(goal_value), inline=False)

            milestone_embed.add_field(
                name=f"Unlock{'ed' if complete else 's'}", value=milestone.unlock_text, inline=False
            )

            if all_complete and complete and milestone.completion_text:
                milestone_embed.add_field(name="Completed", value=milestone.completion_text, inline=False)
                image_endpoint = milestone.completion_image_endpoint
                milestone_embed.color = COMPLETION_EMBED_COLOR

            milestone_embed.set_image(url=self.bot.data.asset(image_endpoint))

            if milestone.quest.event.startswith("sigil"):
                footer.append(
                    "Earn the exclusive Halloween 2023 badge by contributing a certain amount to milestones that require sigils (total)!"
                )

            milestone_embed.set_footer(text="\n".join(footer))

            return milestone_embed

        pages = ContinuablePages(FunctionPageSource(len(milestones), get_page), allow_go=False, loop_pages=False)
        pages.current_page = current_milestone_page
        await pages.start(ctx)

    @checks.has_started()
    @halloween.command(aliases=("inv", "satchel", "satchels", "sigil", "sigils"))
    async def inventory(self, ctx: PoketwoContext):
        embed = self.bot.Embed(title=f"Halloween 2023 Inventory")
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        satchel_text = ""
        sigil_text = ""
        for satchel, sigil in SATCHEL_SIGILS.items():
            if not await self.satchel_unlocked(satchel):
                continue
            satchel_text += f'- {getattr(FlavorStrings, satchel)} - **{member[f"{HALLOWEEN_PREFIX}{satchel}"]:,}**\n'
            sigil_text += f'- {getattr(FlavorStrings, sigil)} - **{member[f"{HALLOWEEN_PREFIX}{sigil}"]:,}**\n'

        prefix = ctx.clean_prefix.strip()
        embed.add_field(
            name="Satchels",
            value=(
                "> Various types of satchels will show up as you catch specific types of pokémon once they're unlocked from milestones."
                f" These satchels hold various rewards to aid you in your journey to save the Golurk!\n> {CMD_OPEN.format(prefix)}"
                f"\n{satchel_text or NOTHING}"
            ),
            inline=False,
        )
        embed.add_field(
            name="Sigils",
            value=textwrap.dedent(
                "> Sigils, obtained from satchels, can be offered to advance specific milestones to help the Sinister Sages in their mission."
                f" You can earn rewards and an exclusive badge when offering them to commemorate your contributions!\n> {CMD_OFFER.format(prefix)}"
                f"\n{sigil_text or NOTHING}"
            ),
            inline=False,
        )

        await ctx.send(embed=embed)

    @commands.is_owner()
    @halloween.command(aliases=("givesatchel",), usage="<satchel> [qty=1]")
    async def addsatchel(
        self,
        ctx: PoketwoContext,
        user: FetchUserConverter,
        *,
        satchel_and_qty: ItemAndQuantityConverter(SATCHEL_IDS, valid_string(SATCHEL_IDS.values())),
    ):
        """Give satchels to a user."""

        satchel, qty = satchel_and_qty
        satchel_name = getattr(FlavorStrings, satchel)

        await self.bot.mongo.update_member(user, {"$inc": {f"{HALLOWEEN_PREFIX}{satchel}": qty}})
        await ctx.send(f"Gave **{user}** {qty}x {satchel_name:b}.")

    def sigil_milestones(self) -> Tuple[Milestone]:
        return [m for m in self.MILESTONES if m.quest.event.startswith("sigil")]

    @checks.has_started()
    @halloween.command(usage="<satchel> [qty=1]")
    async def open(
        self,
        ctx: PoketwoContext,
        *,
        satchel_and_qty: ItemAndQuantityConverter(SATCHEL_IDS, valid_string(SATCHEL_IDS.values())) = None,
    ):
        if satchel_and_qty is None:
            return await ctx.invoke(self.inventory)

        satchel, qty = satchel_and_qty
        satchel_name = getattr(FlavorStrings, satchel)

        if qty <= 0:
            return await ctx.send(f"Nice try...")
        elif qty > 15:
            return await ctx.send("You can only open up to 15 satchels at once!")

        member = await self.bot.mongo.fetch_member_info(ctx.author)

        inventory_amount = member[f"{HALLOWEEN_PREFIX}{satchel}"]

        if inventory_amount < qty:
            return await ctx.send(
                f"You don't have enough {satchel_name}! Wild Pokémon sometimes drop them when caught."
            )

        # GO
        await self.bot.mongo.update_member(ctx.author, {"$inc": {f"{HALLOWEEN_PREFIX}{satchel}": -qty}})

        embed = self.bot.Embed(
            title=f"You open {qty} {satchel_name:{'s' if qty > 1 else ''}}...",
            description=None,
        )
        embed.set_author(icon_url=ctx.author.display_avatar.url, name=str(ctx.author))

        sigil_type = f"{HALLOWEEN_PREFIX}{SATCHEL_SIGILS[satchel]}"
        update = {"$inc": {"balance": 0, sigil_type: 0}}
        inserts = []
        text = []

        drop_sigil = not all([await m.is_complete() for m in self.sigil_milestones()])
        for reward in random.choices(SATCHEL_REWARDS, weights=SATCHEL_WEIGHTS, k=qty):
            count = random.choice(SATCHEL_REWARD_AMOUNTS[reward])

            match reward:
                case "pc":
                    text.append(f"- {count} {FlavorStrings.pokecoins:!e}")
                    update["$inc"]["balance"] += count
                case "sigil":
                    if drop_sigil:
                        text.append(f"- {getattr(FlavorStrings, SATCHEL_SIGILS[satchel])}")
                        update["$inc"][sigil_type] += 1
                    else:
                        count = round(random.choice(SATCHEL_REWARD_AMOUNTS["pc"]) / 2)
                        text.append(
                            f"- {getattr(FlavorStrings, SATCHEL_SIGILS[satchel])} -> {count} {FlavorStrings.pokecoins:!e}"
                        )
                        update["$inc"]["balance"] += count
                case "event-sage" | "non-event" | "non-event-shiny":
                    shiny_boost = 1
                    if reward in ("non-event", "non-event-shiny"):
                        pool = [x for x in self.pools["non-event"] if x.catchable]
                        species = random.choices(pool, weights=[x.abundance for x in pool], k=1)[0]
                        if reward == "non-event-shiny":
                            shiny_boost = 4096  # Guarantee shiny
                    elif reward == "event-sage":
                        # Sage
                        shiny_boost = 5  # 5x shiny boost for sages
                        species = self.pools[satchel][0]
                    pokemon = await self.make_pokemon(ctx.author, member, species=species, shiny_boost=shiny_boost)
                    pokemon_obj = self.bot.mongo.Pokemon.build_from_mongo(pokemon)

                    text.append(f"- {pokemon_obj:liP}")
                    inserts.append(pokemon)
                case "nothing":
                    text.append("- Empty... 👻")

        await self.bot.mongo.update_member(ctx.author, update)
        if len(inserts) > 0:
            await self.bot.mongo.db.pokemon.insert_many(inserts)

        embed.description = "\n".join(text)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.is_owner()
    @halloween.command(aliases=("givesigil",), usage="<sigil> [qty=1]")
    async def addsigil(
        self,
        ctx: PoketwoContext,
        user: FetchUserConverter,
        *,
        sigil_and_qty: ItemAndQuantityConverter(SIGIL_IDS, valid_string(SIGIL_IDS.values())),
    ):
        """Give sigils to a user."""

        sigil, qty = sigil_and_qty
        sigil_name = getattr(FlavorStrings, sigil)

        await self.bot.mongo.update_member(user, {"$inc": {f"{HALLOWEEN_PREFIX}{sigil}": qty}})
        await ctx.send(f"Gave **{user}** {qty}x {sigil_name:b}.")

    async def give_badge(self, ctx: PoketwoContext):
        user = ctx.author
        member = await self.bot.mongo.fetch_member_info(user)
        if member.badges.get(BADGE_NAME):
            return

        sigil_milestones = self.sigil_milestones()
        requirement = round(BADGE_REQ_PERCENT * sum([await m.get_goal() for m in sigil_milestones]))
        total_contribution = sum([member[m.contribution_id] for m in sigil_milestones])

        if total_contribution >= requirement:
            await self.bot.mongo.update_member(user, {"$set": {f"badges.{BADGE_NAME}": True}})
            await ctx.reply(
                f"Congratulations! You have earned the exclusive **Halloween 2023** badge for your sigil contributions to the community milestones!"
            )

    @checks.has_started()
    @halloween.command(usage="<sigil> [qty=1]")
    async def offer(
        self,
        ctx: PoketwoContext,
        *,
        sigil_and_qty: ItemAndQuantityConverter(SIGIL_IDS, valid_string(SIGIL_IDS.values())) = None,
    ):
        """Offer sigils towards current milestone, if applicable."""

        if sigil_and_qty is None:
            return await ctx.invoke(self.inventory)

        sigil, qty = sigil_and_qty
        sigil_name = getattr(FlavorStrings, sigil)

        if qty <= 0:
            return await ctx.send(f"Nice try...")

        member = await self.bot.mongo.fetch_member_info(ctx.author)
        current_milestone = await self.get_current_milestone()
        if await current_milestone.is_complete():
            return await ctx.send("The current milestone has already been completed!")

        progress = await current_milestone.get_progress()
        goal = await current_milestone.get_goal()

        if current_milestone.quest.event.split("_")[0] != "sigil":
            return await ctx.send("The current milestone does not require sigils!")

        effect = 1 if current_milestone.quest.event == sigil else 0.5
        qty = math.ceil(min(qty, (goal - progress) / effect))
        inc = qty * effect
        pc = round(sum([random.choice(SATCHEL_REWARD_AMOUNTS["pc"]) * effect for _ in range(qty)]))

        sigil_inventory_field = f"{HALLOWEEN_PREFIX}{sigil}"
        if member[sigil_inventory_field] < qty:
            return await ctx.send(
                f"You don't have enough {sigil_name:sb} to offer. Try catching some more Pokémon and opening {getattr(FlavorStrings, SIGIL_SATCHELS[sigil]):sb}!"
            )

        await current_milestone.increment_progress(inc, user=ctx.author)
        await self.bot.mongo.update_member(
            ctx.author,
            {"$inc": {sigil_inventory_field: -qty, "balance": pc}},
        )
        await ctx.send(
            f"You offered {qty} {sigil_name:b{'s' if qty > 1 else ''}} towards *{current_milestone.title}*! You've earned **{pc:,}** {FlavorStrings.pokecoins}."
        )
        await self.give_badge(ctx)

    @checks.is_developer()
    @halloween.command(aliases=("setgoal",))
    async def editgoal(self, ctx: PoketwoContext, milestone_number_or_id: Union[int, str], goal: int):
        """Edit the goal of a milestone by number or id. Cannot edit currently progressing or previously completed milestones."""

        valid_ids = ", ".join([f"`{m.id}`" for m in self.MILESTONES])
        match milestone_number_or_id:
            case str():
                milestone = get(self.MILESTONES, id=milestone_number_or_id)
                if milestone is None:
                    return await ctx.send(f"Invalid milestone id provided. Valid ids: {valid_ids}.")
            case int():
                if not (0 < milestone_number_or_id <= len(self.MILESTONES)):
                    return await ctx.send(
                        f"Invalid milestone index provided. Valid indexes: `1-{len(self.MILESTONES)}`."
                    )
                milestone = self.MILESTONES[milestone_number_or_id - 1]
            case _:  # This should be impossible but why not
                return await ctx.send(
                    f"Invalid milestone input. Please make sure it is either the number (`1-{len(self.MILESTONES)}`) or the id ({valid_ids}) of the milestone"
                )

        if goal <= 0:
            return await ctx.send(f"The goal cannot be less than or equal to 0!")

        current_milestone_index = self.MILESTONES.index(await self.get_current_milestone())
        milestone_index = self.MILESTONES.index(milestone)
        if not (current_milestone_index < milestone_index):
            return await ctx.send("Cannot edit the goal of the current or previous milestones!")

        heading = f"**Community Milestone {milestone_index + 1}: {milestone.title}**"

        current_goal = await milestone.get_goal()
        if current_goal == goal:
            return await ctx.send(f"The goal of the milestone {heading} is already **{goal:,}**!")

        result = await ctx.confirm(
            textwrap.dedent(
                f"""
                Are you sure you want to change the goal of the following milestone from **{current_goal:,}** to **{goal:,}**?

                {heading}
                **Goal**: {milestone.get_goal_text(current_goal)}
                """
            )
        )
        if not result:
            return await ctx.send("Aborted.")

        await milestone.set_goal(goal)
        await ctx.send(
            f"Successfully changed the goal of milestone {heading} from **{current_goal:,}** to **{goal:,}**."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Halloween(bot))
