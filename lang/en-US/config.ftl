config-embed =
  .title = Server Configuration
  .field-level-up-name = Display level-up messages? {$silenceCommand}
  .field-location-name = Location {$locationCommand}
  .field-spawning-channels-name = Spawning Channels {$redirectCommand}
  .field-spawning-channels-value = All Channels

config-yes = Yes
config-no = No
command-example-silence = serversilence
command-example-location = location <location>
command-example-redirect = redirect <channel 1> <channel 2> ...

silence-on = I'll no longer send level up messages. You'll receive a DM when your {-pokemon} evolves or reaches level 100.
silence-off = Reverting to normal level up behavior.
serversilence-off = Level up messages are no longer disabled in this server.
serversilence-on = Disabled level up messages in this server. I'll send a DM when {-pokemon} evolve or reach level 100.

redirect-requires-channels = Please specify channels to redirect to!
redirect-completed = Now redirecting spawns to {$channels}

reset-completed = No longer redirecting spawns.
location-current = The server's current location is **{$location}** ({$latitude}, {$longitude}).
unknown-location = Couldn't find that location!
set-location = Set server location to **{$location}** ({$latitude}, {$longitude}).

time-day-title = Time: Day ☀️
time-night-title = Time: Night 🌛
time-day-description = It is currently day time in this server.
time-night-description = It is currently night time in this server.
server-location-field-name = Server Location
server-location-field-value =
  {$location}
  {$latitude}, {$longitude}
