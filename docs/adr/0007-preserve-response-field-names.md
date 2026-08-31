# Preserve response field names

Semantic policy will choose and order compact default projections without renaming response fields; nested scalar selections use their exact dotted JSON paths. A translated vocabulary such as `user.login` to `author` was rejected because it obscures the connected instance's contract and makes explicit `--fields` requests harder to predict.
