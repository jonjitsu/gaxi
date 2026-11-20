# gaxi

gaxi is an AXI bridge for Gitea-compatible instances. It turns one concrete
caller request into exactly one capability that a connected instance
advertises. Instance facts come from the Swagger 2.0 description, read at
runtime. Local semantic policy supplies the AXI behavior that description does
not state, such as whether an operation is destructive and which fields a list
shows. gaxi is not a generated API client, and it does not ship a checked-in
command catalog. The contract is [AXI](https://axi.md).

gaxi requires Python 3.13 or newer and has no runtime dependencies outside the
standard library. The license is MIT. The package version is the `version`
field in `pyproject.toml`.

## Key features

- With no arguments, `gaxi` prints the live home view. `gaxi --help` prints usage.
- A request resolves to one advertised capability. `gaxi capabilities` lists that catalog, and `gaxi capability` inspects one entry.
- Structured output defaults to TOON. TOON and YAML encode the projected
  logical result. For one successful collection or object, `--output json`
  prints the decoded body and skips the default projection and truncation at
  160 Unicode characters. In JSON, a batch is one array of result rows, and
  `--fields` selects from those rows.
- Results use a projection. `--fields` replaces it. `--full` disables truncation of fields that are already projected.
- Execution policy keeps effect, confirmation, and retry separate. A known
  destructive mutation requires `--yes`. A mutation with unknown semantics
  requires `--allow-unknown`. `--dry-run` resolves, binds, and validates, then
  skips the API operation. Swagger discovery can still fetch the description.
- Git remotes supply the instance origin and the `owner/repo` identity.
- A token is bound to one exact origin, either by `GITEA_SERVER` together with `GITEA_TOKEN` or by an external credential helper.
- `gaxi context` prints ambient context. `gaxi skill` prints generated Agent Skill text. `gaxi setup` writes that skill or an opt-in session hook.

## Installation

Install from the Nix flake, from a clone with uv, or from the GitHub release
wheel. gaxi requires Python 3.13 or newer.

### Nix

The public flake is the repository root. `package.nix` exposes the package as
`packages.default`. `packages/gaxi` is the `gaxi` attribute.

```shell
nix build .#gaxi
nix run .#gaxi -- --help
nix flake check --no-build
```

`nix run` takes program arguments after `--`. `nix build` and `nix run` with
no attribute build the same package. `nix flake check --no-build` evaluates
the current system's flake outputs, including the development shell, and does
not build checks. `--all-systems` checks every system. The Quickstart calls
`gaxi`. From this flake, run `nix run .#gaxi --`.

### From a clone

Sync every dependency group:

```shell
uv sync --all-groups
```

The check workflow syncs from the lockfile:

```shell
uv sync --all-groups --frozen
```

The console script is `gaxi`. `python -m gaxi` runs the same program.

```shell
uv run gaxi --help
uv run python -m gaxi --help
```

The Quickstart calls `gaxi`. From this clone, run `uv run gaxi`.

### Release wheel

The `release-mirror` workflow builds `gaxi-<version>-py3-none-any.whl` from the
tagged tree and attaches it to the GitHub release for `github.com/jonjitsu/gaxi`.
The tag is the version declared in `pyproject.toml`, with no `v` prefix.

```text
https://github.com/jonjitsu/gaxi/releases/download/<version>/gaxi-<version>-py3-none-any.whl
```

The wheel needs a Python 3.13 or newer environment. Create one with uv, or
select an interpreter you already have:

```shell
uv venv --python 3.13
uv pip install --python .venv "https://github.com/jonjitsu/gaxi/releases/download/<version>/gaxi-<version>-py3-none-any.whl"
.venv/bin/gaxi --help
```

`uv venv --python 3.13` creates `.venv` on Python 3.13. Pass an existing
interpreter to `--python` when you want that interpreter instead. The
Quickstart calls `gaxi`. After this install, run `.venv/bin/gaxi`, or `gaxi`
when `.venv/bin` is on `PATH`.

A uv project can pin the same URL under `[tool.uv.sources]`. This repository
pins the `python-codeforge` wheel that way.

## Quickstart

These examples call `gaxi`. Use `nix run .#gaxi --` for the Nix flake,
`uv run gaxi` for a clone, or `.venv/bin/gaxi` after the wheel install.

`--server` applies to one invocation. Export `GITEA_SERVER` so later commands
keep the instance, or pass `--server` on each command that needs one.
`gaxi auth add` stores a helper for the origin you name. It does not set
`default_server`. The full selection order is under
[Configuration](#configuration).

```shell
export GITEA_SERVER=https://gitea.example.com
printf '%s\n' "$TOKEN" | gaxi auth add "$GITEA_SERVER" --token-stdin --helper "<command>"
gaxi
```

Pass `--helper "<command>"` when no helper is configured for the origin.
`auth add` reads the token from stdin. A pipe or a quoted heredoc supplies
it. Never pass the token as an argument.

```shell
gaxi auth add "$GITEA_SERVER" --token-stdin --helper "<command>" <<'EOF'
<token>
EOF
```

To carry the instance on each command instead of exporting it, repeat
`--server`:

```shell
printf '%s\n' "$TOKEN" | gaxi auth add https://gitea.example.com --token-stdin --helper "<command>"
gaxi --server https://gitea.example.com
```

With no arguments, gaxi prints the home view. The view shows the executable
path, the summary, the server, the instance version, the `identity`, and the
number of available capabilities. The repository name is the `origin` remote's
`owner/repo` value, or the first remote's value when `origin` is absent. When
that name is present, the view also shows the branch and the open issue and
pull counts. The version, the branch, and those counts can be `unknown`.

```text
gaxi
```

Each search argument must occur in the method, path, summary, `operationId`, or tags:

```text
gaxi capabilities pull request
```

Read one capability by a concrete API-relative path:

```text
gaxi get /repos/acme/widgets/pulls state=open limit=20
```

`delete` always requires `--yes` on the same command. gaxi does not prompt.

```text
gaxi delete /repos/acme/widgets/issues/comments/17 --yes
```

## Configuration

### Instance

gaxi selects one origin and stops at the first match:

1. `--server`
2. `GITEA_SERVER`
3. The Git `origin` remote, when that remote maps to an instance origin
4. The other remotes, when they map to exactly one origin
5. `default_server` in `config.json`

An `http` or `https` remote contributes its own origin. An SSH remote uses
the first `ssh_hosts` value that matches the host, ignoring case. That server
entry's origin wins, including when a later entry lists the same host. gaxi
uses `https://` plus the host only when no `ssh_hosts` entry matches. When no
source matches, the command prints a structured error before it contacts the
instance.

Repository context is the origin, owner, and repository taken from those
remotes. gaxi only reads Git state.

### Credentials

Set `GITEA_TOKEN` only together with `GITEA_SERVER`. Setting `GITEA_TOKEN`
without `GITEA_SERVER` is an error when a command resolves a credential.
Otherwise gaxi selects the environment token when `GITEA_SERVER` equals the
request origin. When that match fails, gaxi asks the credential helper for
the request origin and uses a token the helper returns. When the environment
token is bound to another origin and the helper returns no token, gaxi
blocks the API operation. Swagger discovery can still run before that check.
When `GITEA_TOKEN` is unset and the helper returns no token, the request is
anonymous.

Credential selection uses an exact origin match. A followed GET redirect
keeps `Authorization` when the target starts with the origin, and drops it
otherwise.

Store a helper token with:

```shell
printf '%s\n' "$TOKEN" | gaxi auth add https://gitea.example.com --token-stdin --helper "<command>"
```

The helper is an external command. gaxi runs `<helper> get <origin>`,
`<helper> store <origin>`, or `<helper> erase <origin>`. `gaxi auth list`
prints each configured origin. It also prints the environment credential when
both `GITEA_SERVER` and `GITEA_TOKEN` are set. `gaxi auth remove <origin>`
erases the stored token.

`--anonymous` sends no credential, including when one is bound to the origin.

`gaxi auth allow-insecure <origin>` allows a credential over plaintext HTTP for
that origin. The origin must use the `http` scheme. Until this is set, gaxi
refuses to send a credential to an `http` origin.

### Paths and cache

User configuration is `config.json`. Its directory is `GAXI_CONFIG_HOME` when
that variable is set. Otherwise the directory is `$XDG_CONFIG_HOME/gaxi`, or
`~/.config/gaxi` when `XDG_CONFIG_HOME` is unset.

Cached instance descriptions use `GAXI_CACHE_HOME` when that variable is set.
Otherwise they use `$XDG_CACHE_HOME/gaxi`, or `~/.cache/gaxi` when
`XDG_CACHE_HOME` is unset. `GAXI_CACHE_TTL` is the cache lifetime in seconds.
The default is 3600.

`.gaxi/overlay.json` is the repository overlay. Built-in policy wins when it
sets a presentation field. The user overlay in `config.json`, under
`overlays` for that origin, fills fields that are still unset. The
repository overlay then fills `entity`, `entity_singular`, and `projection`
when built-in policy and the user overlay left them unset. It does not set
confirmation or retry.

### Output

`--output` accepts `toon`, `json`, or `yaml`. The default is `toon`.

TOON and YAML encode the projected logical result, including `count`,
`omitted[]`, and `help[]`. For one successful response classified as a
collection or an object, `--output json` prints the decoded body. That path
skips the default projection and truncation at 160 Unicode characters.
`--fields` limits that body to the named paths and keeps each value as JSON.

A batch is one array of result rows. A successful object response keeps its
fields. A collection response becomes a count row. A status or failure
response becomes a summary row. `--fields` selects from those rows.
`--output json` prints the array. TOON and YAML project the same rows.

For a single response, an error, a status result, or a non-JSON body stays a
structured document in every format. `--raw` emits the successful response
bytes. `--save` emits a receipt after writing the body to a file. A batch
rejects both flags.

`--no-help` omits `help[]` suggestions. `GAXI_NO_HELP` does the same when its
value is `1`, `true`, `yes`, or `on`. An explicit `--help` request still prints
its examples.

`--refresh` fetches the instance description again. `--timeout` is the HTTP
timeout for one request, in seconds. The default is 30. `--debug` writes one
line per HTTP request to stderr, including description discovery. Results and
structured errors go to stdout.

## Usage

The request verbs are `get`, `post`, `put`, `patch`, and `delete`. Each takes
an API-relative path and `name=value` assignments. A known destructive
mutation, including every `delete`, requires `--yes`. A mutation whose
confirmation policy is unknown requires `--allow-unknown`.

```text
gaxi get /repos/acme/widgets/issues/42 --fields number,title,body --full
gaxi post /repos/acme/widgets/issues title="Broken deployment"
gaxi post /repos/acme/widgets/issues --input-json @issue.json
gaxi post /repos/acme/widgets/issues --input-json '[{"title":"First"},{"title":"Second"}]'
gaxi put /user/starred/acme/widgets
gaxi patch /repos/acme/widgets/issues/42 state=closed
gaxi delete /repos/acme/widgets/issues/comments/17 --yes
```

`--input-json` takes one JSON object, a JSON array, or NDJSON with one object
per line. An array or NDJSON sends one request per element against the same
capability. A failing element remains in the result, and the command exits
non-zero. A destructive batch takes `--yes` once for the whole invocation.
`--save` and `--raw` are rejected for a batch, and those two flags cannot be
combined on any request. `--save <path>` streams one response body to a file
and prints a receipt. `--overwrite` lets that write replace an existing file.
`--raw` writes the successful response bytes to stdout. `--dry-run` resolves,
binds, and validates, then skips the API operation. Swagger discovery can
still fetch the description. The [CLI reference](docs/cli.md) says
`--dry-run` resolves, binds, and validates without sending a request.

Pass `--as <method:path-template>` or `--operation <operationId>` when the
most specific matching capabilities tie. When one match is more specific than
the others, gaxi selects it without those flags.

```text
gaxi capabilities delete issue
gaxi capability get:/repos/{owner}/{repo}/pulls
gaxi capability repoListPullRequests
gaxi context
gaxi skill
gaxi setup skill
gaxi setup skill --path .claude/skills/gitea/SKILL.md
gaxi setup hook
```

`gaxi context` prints the compact context an agent reads before acting.
`gaxi skill` prints Agent Skill Markdown on stdout and includes no credential
material. `gaxi setup skill` writes that skill to
`.claude/skills/gitea-axi-bridge/SKILL.md` unless you pass `--path`. A
relative `--path` is resolved from the repository root, or from the current
directory when you are not in a repository. `gaxi setup` creates missing
parent directories. `gaxi setup hook` adds a `SessionStart` hook to
`.claude/settings.json`. The hook runs `gaxi context`. A matching hook entry
is kept. `--path` selects another destination. `--overwrite` replaces an
existing skill file.

Successful commands exit 0. Ordinary failures exit 1. That includes an HTTP
failure, a missing acknowledgement, and a missing capability. A missing
capability exits 1 before the operation. Exit 2 is a usage or validation
error, including some post-response checks. An unknown response field exits 2
after the API request. The [CLI reference](docs/cli.md) describes exit 2 as
an unknown command or option, or input rejected before a request was sent.

Flag tables and output shapes are in the [CLI reference](docs/cli.md).
Regenerate it with `uv run invoke docs`.

## Development

Enter the public development shell at the repository root:

```shell
nix develop
```

The shell provides Python 3.13, uv, ruff, nixfmt, Node.js 24, and git. It sets
`UV_PYTHON_DOWNLOADS=never`, so uv uses the shell's interpreter. On NixOS it
also sets `LD_LIBRARY_PATH` so the development-group binary wheels can load.

Sync, then run the quality gate:

```shell
uv sync --all-groups
uv run invoke verify
```

The check workflow syncs with `uv sync --all-groups --frozen`.
`uv run invoke verify` runs the python-codeforge `check` gate, then
`docs-check`. `uv run invoke docs` rewrites `docs/cli.md`.
`uv run invoke docs-check` fails when that file is stale.

Tests live in `tests/gaxi/unit`, `tests/gaxi/properties`, and
`tests/gaxi/integration`. The integration suite is marked `network`. It skips
when `GAXI_TEST_SERVER` is unset or empty. When that variable names an
instance that cannot be reached, setup fails and the suite does not skip.
Continuous integration runs it with `uv run pytest tests/gaxi/integration`.
The Nix package check runs `tests/gaxi/unit` and `tests/gaxi/properties` only.

## Project layout

`src/gaxi` is the installed package. Tests live in `tests/gaxi/unit`,
`tests/gaxi/properties`, and `tests/gaxi/integration`. `docs/` holds the CLI
reference, the architecture map, and the decision records. `tasks.py` is the
Invoke entry point. `automation/` holds those tasks and is not part of the
wheel. `flake.nix` is the Nix flake. `package.nix` and `packages/gaxi` define
the package. `devshells/default.nix` is the public development shell.
`pyproject.toml` declares the version and the `gaxi` console script. Module
details are in the [architecture map](docs/architecture.md).

## Further reading

- [CLI reference](docs/cli.md)
- [Architecture map](docs/architecture.md)
- [Architecture decisions](docs/adr/)
- [Design documents](docs/design/)
- [Domain language](CONTEXT.md)
- [Agent instructions](AGENTS.md)
- [Changelog](CHANGELOG.md)
- [AXI](https://axi.md)
- [MIT license](LICENSE)
