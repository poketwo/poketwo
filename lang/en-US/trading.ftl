scam-identified-and-deleted = **Warning:** A trading embed by a bot pretending to be Pokétwo was identified and deleted for safety. Unattentive players are scammed using fake bots every day. Please make sure you are trading what you intended to.
scam-identified = **Warning:** A trading embed by a bot pretending to be Pokétwo was identified. Unattentive players are scammed using fake bots every day. Please make sure you are trading what you intended to.

## Initiating a trade
already-in-a-trade = You are already in a trade!
user-already-in-a-trade = **{$user}** is already in a trade!
user-is-suspended = **{$user}** is suspended from the bot!
requesting-a-trade = Requesting a trade with {$mention}. Click the checkmark to accept!
trade-request-timed-out = The request to trade has timed out.
user-who-sent-request-is-already-trading = Sorry, the user who sent the request is already in another trade.
cannot-accept-trade-while-trading = Sorry, you can't accept a trade while you're already in one!

## Trade UI
attempting-to-cancel-trade = Attempting to cancel trade...
trade-has-been-canceled = The trade has been canceled.
trade-needs-redeems = The trade could not be executed as one user does not have enough redeems.
trade-needs-pokecoins = The trade could not be executed as one user does not have enough Pokécoins.
trade-between = Trade between {$a} and {$b}
trade-completed = ✅ Completed trade between {$a} and {$b}.
executing-trade = Executing trade...
trade-footer =
  Showing page {$page} out of {$numPages}.
  Reminder: Trading Pokécoins or {-pokemon} for real-life currencies or items in other bots is prohibited and will result in the suspension of your {-brand} account!
trade-none = None
trade-none-on-this-page = None on this page
trade-pokecoins =
  {$coins ->
    [one] 1 Pokécoin
    *[other] {NUMBER($coins)} Pokécoins
  }
trade-redeems =
  {$redeems ->
    [one] 1 redeem
    *[other] {NUMBER($redeems)} redeems
  }
trade-page-line = `{$index}`  **{$species}**　•　Lvl. {$level}　•　{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)}%
trade-page-line-shiny = `{$index}`  **✨ {$species}**　•　Lvl. {$level}　•　{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)}%

## Shared messages:
amount-must-be-positive = The amount must be positive!
same-channel-to-add = You must be in the same channel to add items!
same-channel-to-remove = You must be in the same channel to remove items!
not-in-trade = You're not in a trade!
trade-loading = The trade is currently loading...

trade-unknown-item = {$thing}: Couldn't find that item!
trade-unknown-pokemon = {$thing}: Couldn't find that {-pokemon}!

## Command: trade confirm
trade-was-recently-modified = The trade was recently modified. Please wait a few seconds, and then try again.

## Command: trade add
add-command-for-pokemon-only = {COMMAND("trade add <ids>")} is now only for adding {-pokemon}. Please use the new {COMMAND("trade add pc <amount>")} instead!
trade-add-cannot-trade-selected-pokemon = {$thing}: You can't trade your selected {-pokemon}!
trade-add-cannot-trade-favorited-pokemon = {$thing}: You can't trade favorited {-pokemon}!
trade-add-invalid-item-to-add = {$thing}: That's not a valid item to add to the trade!
trade-add-pokemon-already-in-trade = {$thing}: This {-pokemon} is already in the trade!
not-enough-redeems = You don't have enough redeems for that!
trade-add-firm-refusal = {$thing}: NO

## Command: trade remove pokecoins
not-that-many-pokecoins = There aren't that many Pokécoins in the trade!

## Command: trade remove
trade-remove-invalid-item = {$thing}: That's not a valid item to remove from the trade!
remove-command-for-pokemon-only = {COMMAND("trade remove <ids>")} is now only for adding {-pokemon}. Please use the new {COMMAND("trade remove pc <amount>")} instead!

## Command: trade remove redeems
not-that-many-redeems = There aren't that many redeems in the trade!

## Command: trade add all
too-many-pokemon-in-trade = There are too many {-pokemon} in this trade! Try adding them individually or seperating it into different trades.
too-many-pokemon-in-trade-use-limit-flag = There are too many {-pokemon} in this trade! Try adding `--limit {$limit}` to the end of your trade.
trade-add-all-confirmation = Are you sure you want to trade **{NUMBER($number)} {-pokemon}**? Favorited and selected {-pokemon} won't be added.
trade-add-all-in-progress = Adding {NUMBER($number)} {-pokemon}, this might take a while...

## Command: trade info
couldnt-find-pokemon-in-trade = Couldn't find that {-pokemon} in the trade!
trade-info-embed =
  .field-details-name = Details
  .field-details-value =
    {"*"}*XP:** {$xp}/{$maxXp}
    {"*"}*Nature:** {$nature}
  .field-stats-name = Stats
  .field-stats-value =
    {"*"}*HP:** {$hp} – IV: {$ivHp}/31
    {"*"}*Attack:** {$atk} – IV: {$ivAtk}/31
    {"*"}*Defense:** {$defn} – IV: {$ivDefn}/31
    {"*"}*Sp. Atk:** {$satk} – IV: {$ivSatk}/31
    {"*"}*Sp. Def:** {$sdef} – IV: {$ivSdef}/31
    {"*"}*Speed:** {$spd} – IV: {$ivSpd}/31
    {"*"}*Total IV:** {NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)}%
  .field-held-item = Held Item
  .footer-text = Displaying {-pokemon} {$number} of {$tradingPartner}.
