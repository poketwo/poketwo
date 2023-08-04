suspended-users = Suspended {$users}.
temporarily-suspended-users = Suspended {$users} for {$duration}.
unsuspended-users = Unsuspended {$users}.
addredeem-completed = {$redeems ->
  [one] Gave **{$user}** {$redeems} redeem.
  *[other] Gave **{$user}** {$redeems} redeems.
}
addcoins-completed = {$coins ->
  [one] Gave **{$user}** {$coins} Pokécoin.
  *[other] Gave **{$user}** {$coins} Pokécoins.
}
addshard-completed = {$coins ->
  [one] Give **{$user}** {$shards} shard.
  *[other] Gave **{$user}** {$shards} shards.
}
addvote-completed = Increased vote streak by {$votes} for **{$user}**.
invalid-box-type = That's not a valid box type!
addbox-completed = {$boxes ->
  [one] Gave **{$user}** {$boxes} {$type} box.
  *[other] Gave **{$user}** {$boxes} {$type} boxes.
}
give-completed = Gave **{$user}** a {$pokemon}.
setup-completed = Gave **{$user}** {$number} {-pokemon}.
