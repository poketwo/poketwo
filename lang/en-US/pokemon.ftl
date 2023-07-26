nickname-too-long = That nickname is too long.
nickname-contains-urls = That nickname contains URL(s).
found-no-pokemon-matching = Found no {-pokemon} matching this search.
found-no-pokemon-matching-excluding-favorited-and-selected = Found no {-pokemon} matching this search (excluding favorited and selected {-pokemon}).

## NOTE: Used in create_filter, which is used by multiple commands.
filter-invalid-numerical = Couldn't parse `--{$flag} {$arguments}`

## Command: reindex
reindexing-pokemon = Reindexing all your {-pokemon}... please don't do anything else during this time.
successfully-reindexed-pokemon = Successfully reindexed all your {-pokemon}!

## Command: nickname
removed-nickname = Removed nickname for your level {$level} {$pokemon}.
changed-nickname = Changed nickname to `{$nickname}` for your level {$level} {$pokemon}.

## Command: nickall
confirm-mass-unnick = Are you sure you want to **remove** nickname for {$number} {-pokemon}?
confirm-mass-nick = Are you sure you want to rename {$number} {-pokemon} to `{$nickname}`?
nickall-in-progress = Renaming {$number} {-pokemon}, this might take a while...
nickall-completed-removed = Removed nickname for {$number} {-pokemon}.
nickall-completed = Changed nickname to `{$nickname}` for {$number} {-pokemon}.

## Command: favorite
already-favorited-pokemon =
  Your level {$level} {$pokemon} is already favorited.
  To unfavorite a {-pokemon}, please use {COMMAND("unfavorite")}.
favorited-pokemon = Favorited your level {$level} {$pokemon}.

## Command: unfavorite
unfavorited-pokemon = Unfavorited your level {$level} {$name}.

## Command: favoriteall
favoriteall-confirm = Are you sure you want to **favorite** your {$number} {-pokemon}?
favoriteall-none-found =
  Found no unfavorited {-pokemon} within this selection.
  To mass unfavorite a {-pokemon}, please use {COMMAND("unfavoriteall")}.
favoriteall-completed =
  Favorited your {$nowFavorited} unfavorited {-pokemon}.
  All {$totalSelected} selected {-pokemon} are now favorited.

## Command: unfavoriteall
unfavoriteall-non-found = Found no favorited {-pokemon} within this selection.
unfavoriteall-confirm = Are you sure you want to **unfavorite** your {$number} {-pokemon}?
unfavoriteall-completed =
  Unfavorited your {$nowUnfavorited} favorited {-pokemon}.
  All {$totalSelected} selected {-pokemon} are now unfavorited.

## Command: info
pokemon-info-embed =
  .field-details-name = Details
  .field-details-value =
    {"*"}*XP:** {$xp}/{$maxXP}
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
  .field-held-item-name = Held Item
  .footer-text =
    Displaying {-pokemon} {$index}.
    ID: {$id}

## Command: select
selected-pokemon = You selected your level {$level} {$species}. No. {$index}.

## Command: order
invalid-order-specifier = Please specify either `iv`, `iv+`, `iv-`, `level`, `level+`, `level-`, `number`, `number+`, `number-`, `pokedex`, `pokedex+` or `pokedex-`
now-ordering-pokemon-by = Now ordering {-pokemon} by `{$sort}`.

## Command: release
cannot-release-selected = {$index}: You can't release your selected {-pokemon}!
cannot-release-favorited = {$index}: You can't release favorited {-pokemon}!
release-failsafe-mismatch = Couldn't find/release {$difference} {-pokemon} in this selection!
release-confirm-single = Are you sure you want to **release** your {$pokemon} No. {$index} for 2 pc?
release-confirm-multiple =
  Are you sure you want to release the following {-pokemon} for {NUMBER($amount)} pc?

  {$pokemon}
# NOTE: $coins is always a multiple of 2
release-completed = You released {$modifiedCount} {-pokemon}. You received {NUMBER($coins)} Pokécoins!

## Command: releaseall
releaseall-confirm = Are you sure you want to release **{$number} {-pokemon}** for {$coins} pc? Favorited and selected {-pokemon} won't be removed.
releaseall-in-progress = Releasing {NUMBER($number)} {-pokemon}, this might take a while...
releaseall-completed = You have released {NUMBER($modifiedCount)} {-pokemon}. You received {$coins} Pokécoins!

## Command: pokemon
pokemon-page-line = `{$paddedNumeral}`  **{$pokemon}**  •　Lvl. {$level}　•　{NUMBER($iv, minimumFractionDigits: 2, maximumFractionDigits: 2)}%
pokemon-page-title = Your {-pokemon}

## Command: pokedex
pokedex-embed =
  .title = Your pokédex
  .description = You've caught {NUMBER($caught)} out of {NUMBER($allTotalPokemon)} {-pokemon}!
  .footer-text = Showing {$beginning}–{$end} out of {NUMBER($totalFiltered)}
pokedex-not-caught-yet = Not caught yet!
pokedex-n-caught = {NUMBER($caught)} caught!
pokedex-orderd-ordera-mutually-exclusive = You can use either --orderd or --ordera, but not both.
pokedex-caught-uncaught-mutually-exclusive = You can use either --caught or --uncaught, but not both.
pokedex-only-one-rarity-flag = You can't use more than one rarity flag!
no-pokemon-on-this-page = There are no {-pokemon} on this page.
pokedex-species-embed =
  .title = #{$dexNumber} — {$species}
  .field-rarity-name = Rarity
  .field-evolution-name = Evolution
  .field-types-name = Types
  .field-region-name = Region
  .field-catchable-name = Catchable
  .field-base-stats-name = Base Stats
  .field-base-stats-value =
    {"*"}*HP:** {$hp}
    {"*"}*Attack:** {$atk}
    {"*"}*Defense:** {$defn}
    {"*"}*Sp. Atk:** {$satk}
    {"*"}*Sp. Def:** {$sdef}
    {"*"}*Speed:** {$spd}
  .field-names-name = Names
  .field-appearance-name = Appearance
pokedex-species-embed-title-shiny = #{$dexNumber} — ✨ {$species}
pokedex-you-havent-caught-yet = You haven't caught this {-pokemon} yet!
pokedex-caught-n-of-this-pokemon = You've caught {NUMBER($amount)} of this {-pokemon}!
pokedex-art-credit =
  Artwork by {$artist}.
  May be derivative of artwork © The {-pokemon} Company.

## Command: unmega
unmega-confirm =
  Are you sure you want to switch **{$pokemon}** back to its non-mega form?
  The mega evolution (1,000 pc) will not be refunded!
unmega-completed = Successfully switched back to non-mega form.
unknown-pokemon = Couldn't find that {-pokemon}!

## Command: evolve
too-many-evolutions-at-once = You can't evolve more than {$limit} {-pokemon} at once!
cannot-be-evolved = Your {$pokemon} can't be evolved!
evolved-compact-line =
  {"*"}*Your {$old} is evolving!**
  Your {$old} has turned into a {$new}!

pagination-market-cannot-jump-to-last-page = Sorry, market does not support going to last page. Try sorting in the reverse direction instead. For example, use {COMMAND("market search --order price")} to sort by price.
pagination-market-command-unsupported = Sorry, market does not support this command. Try sorting in the reverse direction instead. For example, use {COMMAND("market search --order price")} to sort by price.
pagination-market-info-command-unsupported = Sorry, market and info do not support this command. Try further filtering your results instead.
