error-command-no-private-message = This command cannot be used in private messages.

error-command-disabled = Sorry. This command is disabled and cannot be used.

error-command-max-concurrency =
  This command can only be used {$rate} at the same time.
concurrency-scope-globally = globally
concurrency-scope-per = per {$bucket}
concurrency-times =
  {$times ->
    [one] {$times} time {$scope}
    *[other] {$times} times {$scope}
  }

error-bot-missing-permissions =
  💥 Err, I need the following permissions to run this command:
  {$fmt}
  Please fix this and try again.

error-account-suspended-embed =
  .title = Account Suspended
  .description =
    Your account was found to be in violation of the [Pokétwo Terms of Service](https://poketwo.net/terms) and has been blacklisted from Pokétwo.
  .field-expires-name = Expires
  .field-reason-name = Reason
  .field-reason-default-value = No reason provided
  .field-reason-appeals-name = Appeals
  .field-reason-appeals-value =
    If, after reading and understanding the reason provided above, you believe your account was suspended in error, and that you did not violate the Terms of Service, you may submit a [Bot Suspension Appeal](https://forms.poketwo.net/a/suspension-appeal) to request a re-review of your case.
error-no-reason-provided = No reason provided

# Note: Displayed as an error to the user whenever localization goes wrong somehow.
localization-error = Localization Error
