# Rename the bridge to `gaxi`

The distribution, package, and executable are named `gaxi`, replacing the `gax` name
recorded in ADR 0015. The import package is `gaxi`, the console script is `gaxi`, the
environment variables are `GAXI_*`, and the cache directory is `.gaxi-cache`.

The rename is a breaking change for anyone who installed the earlier name: the
executable, every documented environment variable, and the cache location all change,
and no compatibility alias is kept. An alias would have to be carried in the console
script, the environment lookups, and the cache path, and the tool is early enough that
the cost of carrying that indirection outweighs the cost of a reinstall.

Generated documentation and the help surface derive the name from the invoked program
rather than a literal, so `gaxi.naming` needed only its default changed. Note that
`docs/design/gitea-axi-bridge-clean-sheet.md` refers to a source document literally
named `gaxi.md`, which predates this decision and is unrelated to the executable.
