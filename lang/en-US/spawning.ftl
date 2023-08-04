wild-fled = Wild {$pokemon} fled. A new wild {-pokemon} has appeared!
wild-appeared = A wild {-pokemon} has appeared!
guess = Guess the {-pokemon} and type {COMMAND("catch <pokémon>")} to catch it!
incense-footer =
  Incense: Active.
  Spawns Remaining: {$remaining}.

captcha = Whoa there. Please tell us you're human! https://verify.poketwo.net/captcha/{$userId}

## Command: hint
hint = The {-pokemon} is {$hint}.

## Command: catch
wrong-pokemon = That is the wrong {-pokemon}!
already-caught = You have already caught this {-pokemon}!
caught = Congratulations {$trainer}! You caught a level {$level} {$species}!
added-to-pokedex =
  {$coins ->
    [one] Added to Pokédex. You received {$coins} Pokécoin!
    *[other] Added to Pokédex. You received {$coins} Pokécoins!
  }
caught-milestone =
  {NUMBER($number, type: "ordinal") ->
    [one] This is your first {$species}! You received {$coins} Pokécoins.
    [two] This is your second {$species}! You received {$coins} Pokécoins.
    [few] This is your third {$species}! You received {$coins} Pokécoins.
    *[other] This is your {$number}th {$species}! You received {$coins} Pokécoins.
  }
shiny-streak-reset = Shiny streak reset. (**{$streak}**)
shiny-chain = +1 Shiny chain! (**{$streak}**)
shiny-flavor-text = These colors seem unusual... ✨

## Command: togglemention
catch-mentions-off = You will no longer receive catch pings.
catch-mentions-on = You will now be pinged on catches.

## Command: shinyhunt
shinyhunt-embed =
  .title = Shiny Hunt ✨
  .description = You can select a specific {-pokemon} to shiny hunt. Each time you catch that {-pokemon}, your chain will increase. The longer your chain, the higher your chance of catching a shiny one!
  .field-current-name = Currently Hunting
  .field-current-value = Type {COMMAND("shinyhunt <pokémon>")} to begin!
  .field-chain-name = Chain
pokemon-not-catchable-wild = This {-pokemon} can't be caught in the wild!
shinyhunt-already-hunting = You are already hunting this {-pokemon} with a streak of **{$streak}**.
shinyhunt-change-pokemon = Are you sure you want to shiny hunt a different {-pokemon}? Your streak will be reset.
shinyhunt-active = You are now shiny hunting **{$pokemon}**.
