# Bind credentials to an exact origin

Every credential source must bind a token to one normalized Gitea origin; ephemeral agent sessions use the `GITEA_SERVER` and `GITEA_TOKEN` environment variables as a pair. An unscoped token was rejected because repository discovery could otherwise send it to a newly encountered remote; stdin and credential helpers may provide additional storage workflows but must preserve the same origin binding.
