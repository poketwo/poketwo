### Localization for the help command, and commands in general

## Localizations for commands and cogs.

# Note: Currently unused because of a current technical limitation.
command-help-help =
  .help = Show help about the bot, a command, or a category.

## Localization for help command-specific functionality.

help-not-found = No help found…

cog-embed =
  .title = {$cog} Commands

bot-help-embed =
  .title = {-brand} Command Categories (Page {$current}/{$max})

# Note: Used when a cog's name can't be resolved.
cog-fallback-name = Other

# Note: A field title that designates the command's signature (expected arguments).
command-embed-signature = Signature

help-command-command-cta = Use {COMMAND("help <command>")} for more info on a command.
help-command-category-cta = Use {COMMAND("help <category>")} for more info on a category.

categories-embed =
  .title = {-brand} Categories

# Note: Shown in place of a cog's description when no description is available.
categories-no-description = No Description

# Note: Appended to the signature of a command when it receives flags.
command-signature-flags = [args...]
