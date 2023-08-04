unknown-listing = Couldn't find that listing!
not-your-listing = That's not your listing!
listing-no-longer-exists = That listing no longer exists.

## Command: market search
marketplace-title = Pokétwo Marketplace
no-listings-found = No listings found.

## Command: market add
price-must-be-positive = The price must be positive!
price-too-high = Price is too high!
cannot-list-selected = {$index}: You can't list your selected {-pokemon}!
cannot-list-favorited = {$index}: You can't list a favorited {-pokemon}!
add-confirmation =
  Are you sure you want to list your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon} No. {$index}** for **{$price}** Pokécoins?
add-completed =
  Listed your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon} No. {$index}** on the market for **{$price}** Pokécoins.

## Command: market remove
market-remove-confirmation = Are you sure you want to remove your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon}** from the market?
market-remove-completed = Removed your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon}** from the market.

## Command: market buy
cannot-self-buy-listing = You can't purchase your own listing!
buy-confirmation =
  Are you sure you want to buy this **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon}** for **{$price}** Pokécoins?
buy-completed = You purchased a **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon}** from the market for {$price} Pokécoins. Do {COMMAND("info latest")} to view it!
someone-purchased-your-listing = Someone purchased your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon}** from the market. You received {$price} Pokécoins!
market-info-embed =
  .title = {$pokemon}
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
  .field-market-listing-name = Market Listing
  .field-market-listing-value =
    {"*"}*ID:** {$id}
    {"*"}*Price:** {$price} pc
  .footer-text = Displaying listing {$id} from market.
