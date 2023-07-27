## Command: `stopincense`
no-active-incense = There is no active incense in this channel!
confirm-incense-cancellation = Are you sure you want to cancel the incense? You can't undo this!
incense-stopped = Incense has been stopped.

## Command: `open`
not-enough-boxes = You don't have enough boxes to do that!
invalid-box-type = Please type `normal`, `great`, `ultra`, or `master`!
too-many-boxes-at-once =
  {$limit ->
    [one] You can only open {$limit} box at once!
    *[other] You can only open {$limit} boxes at once!
  }
# TODO: The mystery box type shouldn't be a variable, and there should be one
#       message for each kind of box.
opening-box-with-sprite =
  {$amount ->
    [one] Opening {$amount} {$sprite} {$type} Mystery Box...
    *[other] Opening {$amount} {$sprite} {$type} Mystery Boxes...
  }
opening-box-simple =
  {$amount ->
    [one] Opening {$amount} {$type} Mystery Box...
    *[other] Opening {$amount} {$type} Mystery Boxes...
  }
box-reward-field-title = Rewards Received
box-reward-pokecoins =
  {$coins ->
    [one] {$coins} Pokécoin
    *[other] {$coins} Pokécoins
  }
box-reward-redeems =
  {$redeems ->
    [one] {$redeems} redeem
    *[other] {$redeems} redeems
  }
box-reward-pokemon = {$pokemon} ({NUMBER($iv, minimumFractionDigits: 2, maximumFractionDigits: 2)}% IV)

## Command: `balance`
balance-embed =
  .title = {$user}'s balance
  .field-coins-name = Pokécoins
  .field-coins-value = {$coins}
  .field-shards-name = Shards
  .field-shards-value = {$shards}

pokemon-not-holding-item = That {-pokemon} isn't holding an item!
pokemon-already-holding-item = That {-pokemon} is already holding an item!

## Command: `drop`
pokemon-dropped-item = Dropped held item for your level {$level} {$name}.

## Command: `moveitem`
moved-items = Moved held item from your level {$fromLevel} {$fromName} to your level {$toLevel} {$toName}.

## Command: `togglebalance`
balance-now-hidden = Your balance is now hidden in shop pages.
balance-no-longer-hidden = Your balance is no longer hidden in shop pages.

## Command: `shop`
shop-title = {-brand} Shop
shop-title-balance = {-brand} Shop - {coins} Pokécoins
shop-title-balance-shards = {-brand} Shop - {coins} Pokécoins, {shards} Shards
shop-page-cta = Use {COMMAND("shop <page>") to view different pages.
shop-page-1-title = XP Boosters & Candies
shop-page-2-title = Evolution Stones
shop-page-3-title = Form Change Items
shop-page-4-title = Held Items
shop-page-5-title = Nature Mints
shop-page-6-title = Mega Evolutions
shop-page-7-title = Shard Shop
shop-description =
  We have a variety of items you can buy in the shop. Some will evolve your {-pokemon}, some will change the nature of your {-pokemon}, and some will give you other bonuses. Use {COMMAND("buy <item>")} to buy an item!
shop-description-shards =
  Welcome to the shard shop! Shards are a type of premium currency that can be used to buy special items. Shards can be obtained by exchanging Pokécoins or by purchasing them at https://poketwo.net/store.
shop-booster-active = You have an XP booster active that expires in {$expires}.
shop-shiny-charm-active = You have a shiny charm active that expires in {$expires}.

## Command: `buy`
buy-unknown-item = Couldn't find an item called `{$item}`.
cannot-buy-multiple = You can't buy multiple of this item!
not-enough-shards = You don't have enough shards for that!
not-enough-coins = You don't have enough Pokécoins for that!
cannot-overlevel-pokemon = Your selected {-pokemon} is already level {$level}! Please select a different {-pokemon} using {COMMAND("select")} and try again.
item-not-applicable = This item can't be used on your selected {-pokemon}! Please select a different {-pokemon} using {COMMAND("select")} and try again.
pokemon-holding-everstone = This pokémon is holding an Everstone! Please drop or move the item and try again.
xp-booster-already-active = You already have an XP booster active! Please wait for it to expire before purchasing another one.
shiny-charm-already-active = You already have a shiny charm active! Please wait for it to expire before purchasing another one.
purchased-time-remaining = You purchased {$item}! Use {COMMAND("shop")} to check how much time you have remaining.
purchased-shards = You purchased {$shards} shards!
shard-exchange-prompt = Are you sure you want to exchange **{item.cost * qty:,}** Pokécoins for **{qty:,}** shards? Shards are non-transferable and non-refundable!
purchased-redeems = You purchased {$redeems} redeems!
# XXX: When item names are properly localized, then this should be replaced with
#      a selector.
purchased-generic = You purchased a {$item}!
purchased-generic-vowel = You purchased an {$item}!
purchased-for-pokemon-qty = You purchased a {$item} x {$qty} for your {$pokemon}!
purchased-for-pokemon = You purchased a {$item} for your {$pokemon}!
missing-incense-permissions = You must have administrator permissions or a role named Incense in order to do this!
incense-unavailable = Incenses are currently unavailable. This could be due to bot instability or upcoming maintenance. Check the #bot-outages channel in the official server for more details.
incense-already-active = This channel already has an incense active! Please wait for it to end before purchasing another one.
# TODO: Pokémon evolution messages should be in another file.
congratulations = Congratulations {$name}!
pokemon-evolving = Your {$pokemon} is evolving!
pokemon-changing-forms = Your {$pokemon} is changing forms!
pokemon-turned-into = Your {$old} has turned into a {$new}!
new-move = New move!
pokemon-can-now-learn = Your {$pokemon} can now learn {$move}!
pokemon-level-is-now = Your {$pokemon} is now level {$level}!
pokemon-nature-changed = You changed your selected {-pokemon}'s nature to {$nature}!

## Command: embedcolor
pokemon-cannot-use-custom-embed-colors = That {-pokemon} cannot use custom embed colors!
pokemon-current-embed-color = That {-pokemon}'s embed color is currently **{color}**.
embed-color-white-limitation = Due to a Discord limitation, you cannot set the embed color to pure white. Try **#fffffe** instead.
pokemon-embed-color-changed = Changed embed color to **{color}** for your **{pokemon}**.

## Command: redeem
redeem-embed =
  .title = Your redeems: {$redeems}
  .description = You can use redeems to receive any {-pokemon} of your choice. You can receive redeems by purchasing them with shards or through voting rewards.
  .field-command-name = {COMMAND("redeemspawn <pokémon>")}
  .field-command-value = Use a redeem to spawn a {-pokemon} of your choice in the current channel (careful, if something else spawns, it'll be overridden).

## Command: redeemspawn
no-redeems = You don't have any redeems!
cannot-redeem = You can't redeem this {-pokemon}!
cannot-redeem-here = You can't redeemspawn a {-pokemon} here!
