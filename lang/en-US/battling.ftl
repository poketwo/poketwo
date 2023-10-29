already-in-battle = You're already in a battle!
user-already-in-battle = **{$user}** is already in a battle!
not-in-battle = You're not in battle!
battle-canceled = The battle has been canceled.

## Action descriptions
action-flee = Flee from the battle
action-pass = Pass this turn and do nothing.
action-move = Use {$move}
action-switch = Switch to {NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)}% {$species}
selected-action =
  You selected **{$action}**.

  {"*"}*Back to battle:** {$jumpUrl}

## Getting ready to battle
battle-selection-embed =
  .title = Choose your party
  .description =
    Choose **3** {-pokemon} to fight in the battle. The battle will begin once both trainers have chosen their party.
  .footer-text = Use {COMMAND("battle add <pokemon>")} to add a {-pokemon} to the party!
battle-selection-party-field-name = {$trainer}'s Party
battle-selection-party-line = {NUMBER($ivPercentage, minimumFractionDigits: 2, maximumFractionDigits: 2)}% IV {$species} ({$index})
battle-ready-embed =
  .title = 💥 Ready to battle!
  .description = The battle will begin in 5 seconds.

trainers-repeatedly-passing = Both trainers passed three times in a row. I'll end the battle here.
battle-between = Battle between {$firstTrainer} and {$secondTrainer}.
next-round-begins-in =
  {$seconds ->
    [one] The next round will begin in {$seconds} second.
    *[other] The next round will begin in {$seconds} seconds.
  }
battle-ended = The battle has ended.
battle-dm-cta = Choose your moves in DMs. After both players have chosen, the move will be executed.
trainer-pokemon-line-selected = {"*"}*{$pokemon}** • {$hp}/{$maxHp} HP
trainer-pokemon-line = {$pokemon} • {$hp}/{$maxHp} HP

## Mid-battle callouts
opponent-has-fled = {$fleeingTrainer} has fled the battle! {$opponent} has won.
switched-pokemon-title = {$trainer} switched {-pokemon}!
switched-pokemon-text = {$pokemon} is now on the field!
trainer-used-move = {$pokemon} used {$move}!
dealt-damage = {$move} dealt {$damage} damage!
restored-hp = {$pokemon} restored {$healed} HP.
took-damage = {$pokemon} took {$damage} damage.
ailment-inflicted = It inflicted {$ailment}!
missed = It missed!
lowered-user-stat = Lowered the user's **{$stat}** by {$change} stages.
raised-user-stat = Raised the user's **{$stat}** by {$change} stages.
lowered-opponent-stat = Lowered the opponent's **{$stat}** by {$change} stages.
raised-opponent-stat = Raised the opponent's **{$stat}** by {$change} stages.
fainted = Fainted!
pokemon-has-fainted = {$pokemon} has fainted.
won-battle = {$victor} won the battle!

move-request-cta = What should {$pokemon} do?
move-request-action-line = {$action} **{$description}** • {COMMAND($command)}
move-request-invalid-move = That's not a valid move here!

# XXX: This string is spliced into the "selected-action" message (as the $action
# variable), which is bad practice.
action-pass-text = nothing. Passing turn...
challenge-timed-out = The challenge has timed out.
challenging = Challenging {$user} to a battle. Click the checkmark to accept!
challenging-already-battling = Sorry, the user who sent the challenge is already in another battle.
cannot-challenge-while-battling = Sorry, you can't accept a challenge while you're already in a battle!

## Command: battle add
already-enough-pokemon = {$index}: There are already enough {-pokemon} in the party!
pokemon-already-in-party = {$index}: This {-pokemon} is already in the party!

## Command: moves
moves-embed =
  .title = Level {$level} {$pokemon} — Moves
  .description = Here are the moves your {-pokemon} can learn right now. View all moves and how to get them using {COMMAND("moveset")}!
  .field-available-name = Available Moves
  .field-current-name = Current Moves
  .field-current-value = No Moves

unknown-move = Couldn't find that move!

## Command: learn

already-learned-move = Your {-pokemon} has already learned that move!
cannot-learn-move = Your {-pokemon} can't learn that move!
knows-too-many-moves = Your {-pokemon} already knows the max number of moves! Please select a move to replace.
learned-move = Your {-pokemon} has learned {$move}!

## Command: moveset
invalid-pokemon-search-moveset =
  Please either enter the name of a {-pokemon} species, nothing for your selected {-pokemon}, a number for a specific {-pokemon}, or `latest` for your latest {-pokemon}.
moveset-embed =
  .title = {$pokemon} — Moveset
  .footer-text = Showing {$start}–{$end} out of {$totalMoves}.
moveset-embed-footer = 

## Command: moveinfo
unknown-move = Couldn't find a move with that name!
moveinfo-embed =
  .title = {$move}
  .description = {$description}
  .field-target-name = Target
  .field-target-value = {$target}
  .field-power-name = Power
  .field-accuracy-name = Accuracy
  .field-pp-name = PP
  .field-priority-name = Priority
  .field-type-name = Type
  .field-class-name = Class
  .field-class-value = {$damageClass}
