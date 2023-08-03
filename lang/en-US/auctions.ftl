invalid-auction-id = Invalid auction ID.
no-such-auction-with-id = Could not find auction with that ID.
auction-ended = This auction has ended.
auction-ended-already = That auction has already ended.
unknown-auction = Couldn't find that auction!

auction-details = Auction Details
auction-title = Auction #{$id} • {$pokemon}
auction-title-sold = [SOLD] #{$id} • {$pokemon}
auction-pokemon-details-field-name = {-pokemon} Details
auction-info =
  {"*"}*XP:** {$xp}/{$maxXp}
  {"*"}*Nature:** {$nature}
  {"*"}*HP:** {$hp} – IV: {$ivHp}/31
  {"*"}*Attack:** {$atk} – IV: {$ivAtk}/31
  {"*"}*Defense:** {$defn} – IV: {$ivDefn}/31
  {"*"}*Sp. Atk:** {$satk} – IV: {$ivSatk}/31
  {"*"}*Sp. Def:** {$sdef} – IV: {$ivSdef}/31
  {"*"}*Speed:** {$spd} – IV: {$ivSpd}/31
  {"*"}*Total IV:** {NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)}%
auction-info-held-item =
  {"*"}*Held Item:** {$item}
auction-ended-details =
  {"*"}*Winning Bid:** {NUMBER($coins)} Pokécoins
  {"*"}*Bidder:** {$bidder}
won-auction = You won the auction for the **{$pokemon}** with a bid of **{$bid}** Pokécoins (Auction #{$id}).
auction-ended = The auction for your **{$pokemon}** ended with a highest bid of **{$bid}** Pokécoins (Auction #{$id}).
auction-ended-no-bids = The auction for your **{$pokemon}** ended with no bids (Auction #{$id}).

## Command: auction channel
changed-auction-channel = Changed auctions channel to **{$channel}**.

## Command: auction start
must-start-auctions-in-main-server = Sorry, you cannot start auctions outside of the main server at this time.
invalid-starting-bid = The starting bid is not valid.
invalid-bid-increment = The bid increment is not valid.
max-auction-duration =
  {$weeks ->
    [one] The max duration is {$weeks} week.
    *[other] The max duration is {$weeks} weeks.
  }
auctions-not-set-up = Auctions have not been set up in this server. Have a server administrator do {COMMAND("auction channel #channel")}.
cannot-auction-selected = {$index}: You can't auction your selected {-pokemon}!
cannot-auction-favorited = {$index}: You can't auction a favorited {-pokemon}!
auction-confirmation =
  You are auctioning your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon} No. {$index}**:
  {"*"}*Starting Bid:** {NUMBER($startingBid)} Pokécoins
  {"*"}*Bid Increment:** {NUMBER($increment)} Pokécoins
  {"*"}*Duration:** {$duration}
  Auctions are server-specific and cannot be canceled. Are you sure?
auction-confirmed = Auctioning your **{NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)} {$pokemon} No. {$index}**.
# NOTE: Used when no bid has been placed by another person yet.
auction-info-bidding =
  {"*"}*Starting Bid:** {NUMBER($startingBid)} Pokécoins
  {"*"}*Bid Increment:** {NUMBER($increment)} Pokécoins
auction-bid-cta =
  Bid with {COMMAND($command)}
  Ends in {$delta} at

## Command: auction lowerstart
can-only-lower-own-auctions = You can only lower the starting bid on your own auction.
someone-already-bid = Someone has already bid on this auction.
cannot-increase-starting-bid = You may only lower the starting bid, not increase it.
starting-bid-cannot-be-lower-than-increment = You may not set the new starting bid to a value less than your bid increment.
lowerstart-confirmation = Do you want to lower starting bid to **{NUMBER($newStart)} Pokécoins** on the **{$pokemon}**?
lowerstart-completed =
  {$newStart ->
    [one] Lowered the starting bid on your auction to **{NUMBER($newStart)} Pokécoin**.
    *[other] Lowered the starting bid on your auction to **{NUMBER($newStart)} Pokécoins**.
  }

## Command: auction bid
cannot-self-bid = You can't bid on your own auction.
already-highest-bidder = You are already the highest bidder.
bid-minimum =
  {$minimum ->
    [one] Your bid must be at least {NUMBER($minimum)} Pokécoin.
    *[other] Your bid must be at least {NUMBER($minimum)} Pokécoins.
  }
bid-confirmation = Do you want to bid **{NUMBER($bid)} Pokécoins** on the **{$pokemon}**?
you-have-been-outbid = You have been outbid on the **{$pokemon}** (Auction #{$auctionId}). New bid: {NUMBER($bid)} pokécoins.
bid-completed = You bid **{$bid} Pokécoins** on the **{$pokemon}** (Auction #{$auctionId}).
# NOTE: Used when someone places a bid on an auction.
auction-info-bidding-in-progress =
  {"*"}*Current Bid:** {NUMBER($bid)} Pokécoins
  {"*"}*Bidder:** {$bidder}
  {"*"}*Bid Increment:** {NUMBER($increment)} Pokécoins

## Command: auction search
auctions-in = Auctions in {$guild}
auction-search-line-in-progress =
  `{$paddedId}`  **{$pokemon}**  •  {NUMBER($ivTotal, minimumFractionDigits: 2, maximumFractionDigits: 2)}%  •  CB: {NUMBER($currentBid)}  •  BI: {NUMBER($bidIncrement)} pc  •  {$delta}
auction-search-line =
  `{$paddedId}`  **{$pokemon}**  •  {NUMBER($ivTotal, minimumFractionDigits: 2, maximumFractionDigits: 2)}%  •  SB: {NUMBER($startingBid)}  •  {$delta}
no-auctions-found = No auctions found.
