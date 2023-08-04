-pokemon = Pokémon
-pokemon-plural = Pokémon

-pokecoin = Pokécoin
-pokecoin-plural = Pokécoins

-pokedex = Pokédex

-brand = Pokétwo

-command-pick = {COMMAND("pick <pokemon>")}

start-embed =
  .title = Welcome to the world of {-pokemon}!
  .description = To start, choose one of the starter {-pokemon} using the {-command-pick} command.

invite-embed =
  .title = Want to add me to your server? Use the link below!
  .field-invite-name = Invite Bot
  .field-invite-value = https://invite.poketwo.net
  .field-join-name = Join Server
  .field-join-value = https://discord.gg/poketwo

joined-guild-embed =
  .title = Thanks for adding me to your server! 👋
  .description = To get started, do {COMMAND("start")} to pick your starter {-pokemon}. As server members talk, wild {-pokemon} will automatically spawn in the server, and you'll be able to catch them with {COMMAND("catch <pokémon>")}! For a full command list, do {COMMAND("help")}.
  .field-configs-name = Common Configuration Options
  .field-configs-value =
    • {COMMAND("redirect <channel>")} to redirect {-pokemon} spawns to one channel
    • More can be found in {COMMAND("config help")}
  .field-support-name = Support Server
  .field-support-value =
    Join our server at [discord.gg/poketwo](https://discord.gg/poketwo) for support.

vote-timer-refreshed = Your vote timer on **{$provider}** has refreshed. You can now vote again!
vote-timer-visit = Visit {$name}

vote-embed =
  .title = Voting Rewards
  .description = Vote for us on {$providers} to receive mystery boxes! You can vote once per 12 hours on each site. Build your streak to get better rewards!
  .field-claiming-name = Claiming Rewards
  .field-claiming-value = Use {COMMAND("open <normal|great|ultra|master> [amt]")} to open your boxes!
  .footer-text = You will automatically receive your rewards when you vote.
  .field-voting-name = Server Voting
  .field-voting-value = You can also vote for our server [here](https://top.gg/servers/716390832034414685/vote) to receive a colored role.
vote-provider-joiner = {" and "}
vote-can-vote-now = [You can vote right now!]({$url})
vote-can-vote-again-in = You can vote again in **{$time}**.
vote-visit-button = Visit {$provider}
vote-current-streak = Current Streak: {$votes} {$votes ->
    [one] vote!
    *[other] votes!
  }
vote-field-rewards-name = Your Rewards
vote-field-timer-name = {$name} Timer
vote-field-streak-name = Voting Streak
vote-normal-mystery-box = **Normal Mystery Box:** {$gifts}
vote-great-mystery-box = **Great Mystery Box:** {$gifts}
vote-ultra-mystery-box = **Ultra Mystery Box:** {$gifts}
vote-master-mystery-box = **Master Mystery Box:** {$gifts}

botinfo-embed =
  .title = {-brand} Statistics
  .field-servers-name = Servers
  .field-servers-value = {$servers}
  .field-shards-name = Shards
  .field-shards-value = {$shards}
  .field-trainers-name = Trainers
  .field-trainers-value = {$trainers}
  .field-latency-name = Average Latency
  .field-latency-value = {$average} ms

pick-already-chosen = You have already chosen a starter {-pokemon}! View your {-pokemon-plural} with {COMMAND("pokemon")}.
pick-invalid-choice = Please select one of the starter {-pokemon}. To view them, type {COMMAND("start")}.

tos-embed =
  .title = {-brand} Terms of Service
  .description =
    Please read, understand, and accept our Terms of Service to continue. Violations of these Terms may result in the suspension of your account. If you choose not to accept the user terms, you will not be able to use Pokétwo.
  .url = https://poketwo.net/terms
  .footer-text = These Terms can also be found on our website at https://poketwo.net/terms.
tos-disagreed =
  Since you chose not to accept the new user terms, we are unable to grant you access to Pokétwo. If you wish to continue, please re-run the command and agree to our Terms of Service to continue.

pick-congrats =
  Congratulations on entering the world of {-pokemon}! {$species} is your first pokémon. Type {COMMAND("info")} to view it!

pong-donate =
  Pong! **{$ms} ms**

  Tired of bot slowdowns? Running a bot is expensive, but you can help! Donate at https://poketwo.net/store.
pong = Pong! **{$ms} ms**

times-up = Time's up. Aborted.
aborted = Aborted.
nice-try = Nice try...

profile-embed =
  .title = Trainer Profile
  .field-caught-name = {-pokemon-plural} Caught
  .field-badges-name = Badges
profile-no-badges = No badges
profile-caught-category-total = **Total:** {$amount}
profile-caught-category-mythical = **Mythical:** {$amount}
profile-caught-category-legendary = **Legendary:** {$amount}
profile-caught-category-ultra-beast = **Ultra Beast:** {$amount}
profile-caught-category-shiny = **Shiny:** {$amount}

cleanup = {$count ->
  [one] {$count} message was removed.
  *[other] {$count} messages were removed.
}

unknown-pokemon = Couldn't find that {-pokemon}!
no-pokemon-found = No {-pokemon} found.
unknown-pokemon-matching = Could not find a {-pokemon} matching `{$matching}`.
pokemon-must-be-mega = This {-pokemon} is not in mega form!
forbidden-during-trade = You can't do that in a trade!
page-must-be-positive = Page must be positive!
user-hasnt-started = That user hasn't picked a starter {-pokemon} yet!
user-is-suspended = **{$user}** is suspended from the bot!
pokemon-must-be-selected = You must have a {-pokemon} selected!

rarity-mythical = Mythical
rarity-legendary = Legendary
rarity-ultra-beast = Ultra Beast
rarity-event = Event
rarity = Rarity
evolution = Evolution

no-previous-menu-to-navigate = Couldn't find a previous menu to paginate.
no-event-active = There is no event currently active.

pagination-showing-entries-count = Showing entries {$start}–{$end} out of {$total}.
pagination-showing-entries = Showing entries {$start}–{$end}.
pagination-last-jumping-unsupported = Sorry, this does not support going to last page. Try sorting in the reverse direction instead.
