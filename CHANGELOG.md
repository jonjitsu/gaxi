# Changelog

## Unreleased
- Unknown-field validation errors now rank the reported `known` names by
  closeness to the requested field and add a `did_you_mean` detail when one
  candidate is a clear near miss. Projection aliases are limited to real
  response-name pairs (for example `index`/`number`, `login`/`username`), not
  planner path-param identity synonyms such as `login`→`assignee`.
- `--input-json` now accepts a JSON array or NDJSON (one object per line) to
  send one request per element against the same resolved capability. Batch output
  is a collection result (`count: N of N total` plus a table). Partial failures
  continue through the batch, include per-row error fields, and exit non-zero when
  any element fails. Destructive batches still require `--yes` once for the
  whole invocation; `--save` and `--raw` are rejected for batch requests.
  Per-element transport and policy failures are recorded as row errors instead of
  aborting the batch. `put`, `patch`, and `delete` help now declare collection
  output alongside `post`. Batch truncation `help[]` now suggests read-only detail
  fetches for truncated rows instead of replaying the mutation.
- Batch confirmation retries now preserve the original ``--input-json`` payload
  in ``help[]``, and mixed-result tables treat any row with an ``error`` field as
  a failure even when the value is falsey. Batch retry help now single-quotes
  JSON payloads so shell metacharacters are not expanded when copied, keeps
  ``@file`` and ``-`` sources instead of inlining file contents, and collection
  batch elements render a ``count`` column instead of blank default rows.
- Mixed-result field promotion now retains ``error`` and ``status`` columns when
  observed fallback already selected them, so all-error and 204/404 delete batches
  no longer render zero-column tables.
- Bridge options are now a frozen record grouped by consumer seam (`request`,
  `discovery`, `setup`, `output`, `auth`). Coercion and validation live in
  `gaxi.options.build_options` instead of `cli._options`. `--path` maps to
  `setup.path` and no longer aliases `--save`; `cli.main` constructs a new
  session per invocation instead of mutating `session.options` mid-run.
- Add ``--no-help`` and ``GAXI_NO_HELP`` to omit ``help[]`` suggestions from
  structured output without changing any other part of the result shape.
  ``--help`` documents remain ungated because they are an explicit request for
  usage text.
- Structured error output now honours ``--output`` once parsing has succeeded,
  so agents can request JSON or YAML for failures as well as successes.
- Contextual disclosure now lives in `gaxi.suggestions`: one module owns ordering,
  de-duplication, the suggestion cap, and rendering through `naming.executable()`.
  Raising sites name an intent; `Planner` remains the request-shaped source and
  feeds `build()` rather than capping locally. Three separate caps in `render`,
  `results`, and `commands/capabilities` collapse to `MAX_SUGGESTIONS`.
- Field-selection precedence now lives in `gaxi.fields.fields` instead of being
  split across `results`, `policy`, and `projection`. Result shaping calls one
  function; `projection` keeps truncation and dotted-path resolution only.
- Downloading a response body (`--save`) now lives in `gaxi.download` instead of
  result shaping. Streaming, digesting, atomic replace, and the file receipt are
  owned by `save(response, path, overwrite) -> Receipt`; `results` keeps only
  classification-to-document work.
- HTTP status thresholds and integer query parsing now live in `gaxi.http`
  instead of being re-declared across classify, capability, discovery, invoke,
  planner, swagger, and command modules. Removed unused surface that only tests
  reached (`Capability.declares`, `Classification.decode_error`,
  `Param.collection_format`, `invoke.TEXT_LIMIT`, `capability.LAST_REDIRECT`).
- Collection `help[]` detail suggestions now name placeholders after the
  projected identifier column when that column is the detail route parameter or
  a declared synonym (for example `<number>` for `{index}`), instead of blindly
  adopting any identifier-shaped field such as `<id>` on a `{tag}` route.
- `--debug` now logs description-discovery HTTP requests on stderr, not only
  capability calls. Cold cache discovery is typically two requests (discovery
  page plus description document, on the order of hundreds of kilobytes) and is
  cached for ``GAXI_CACHE_TTL`` seconds (default 3600).
- A 403 with a resolved credential now names the credential source in the
  error and suggests checking the authenticated identity instead of
  re-authenticating. `auth add` remains the suggestion for 401 and for 403 when
  no credential was attached.
- After a mutation that returns an object, `help[]` now points at the created
  entity's detail route with the identifier taken from the response payload,
  instead of unrelated sibling collection routes. When the payload carries no
  usable identifier, suggestions fall back to the previous collection-sibling
  behaviour.
- Put a seam between the HTTP exchange and the rendered result. `invoke.fetch`
  resolves, binds, sends, and classifies one request into a `Fetched` value;
  `run_request` is now fetch-then-render. The home view uses three fetches
  instead of hand-decoding responses, so JSON parsing and `X-Total-Count`
  handling live in `classify` alone. The open-issues aggregate keeps the
  `type=issues` qualifier so pull requests are not double-counted. When `/user`
  returns JSON without a `login`, the home view reports the credential as
  unverified.
- Fixed `release-prepare` retitling an unrelated pull request into the release.
  It looked up the standing release pull request with
  `GET /pulls?state=open&head=release/next`, but Gitea's list-pulls declares no
  `head` input and ignores the parameter instead of rejecting it, so the query
  returned every open pull request and `.[0]` took whichever came first. It
  patched pull request #24 — an unrelated fix — into `Release 1.1.1`, and
  merging that left `release/next` with no pull request at all. The head branch
  is now filtered client-side, and the step runs under `set -euo pipefail` and
  refuses empty release notes, the same guard the version lookup already had.

- Stopped running every quality gate twice. `check` triggered on an unfiltered
  `push` as well as `pull_request`, so each commit on a branch ran all three
  jobs for the branch and then the same three for its pull request, and a
  release tag re-ran the suite a third time on a commit already checked twice.
  Measured on the 1.1.0 release commit, the six checks took 264s of wall clock
  against 314s of job time — effectively serialised, half of it duplicated.
  `push` is now limited to `master`, where there is no pull request to stand in
  for it; branch work is gated by `pull_request` alone.
- Recognised `release` as a commit type. `release-prepare` writes
  `release: X.Y.Z`, a type its own checker did not know, so the pipeline
  generated a commit it would report as untyped. That commit is the one the tag
  lands on and so normally falls outside `tag..HEAD`, but a release whose
  tagging failed leaves it inside the window, where the noise would appear
  exactly while someone is debugging the failure.

## 1.1.0

- Mirrored releases to the public GitHub repository. Publishing a tag now pushes
  the tagged commit and the tag to `jonjitsu/gaxi` and opens a GitHub release
  whose body is the same changelog section Gitea publishes, read from the tagged
  tree rather than from master. It is a separate workflow from `release-tag`
  rather than a step inside it: the canonical tag already exists by then, so a
  GitHub outage must not fail the release, and a retry of `release-tag` would
  trip its refusal to retag. Nothing is force-pushed, so a diverged mirror fails
  loudly instead of overwriting work.

- Fixed the release workflows reading the version through a module path that no
  longer exists. They still ran `python -c 'import release; …'` after the
  mechanics moved into `automation/ci/`, and because a failed command
  substitution inside `echo` does not fail the step, the version came out empty
  instead of erroring: the first run opened a pull request titled `Release` and
  committed `release:`. The bump itself was correct, but `release-tag` would
  have tried to create an empty tag. Both workflows now read the version through
  `invoke release-version`, so the shell holds no knowledge of the module
  layout, and the steps run under `set -euo pipefail` and refuse an empty
  version.
- Documented the commit and release contract in `AGENTS.md`: the Conventional
  Commits types the bump is derived from, that the changelog is hand-written
  under `## Unreleased` and published verbatim as release notes, and that the
  proposed version tracks accumulated work rather than being chosen up front.

- Automated releasing behind a standing release pull request. Every merge to
  `master` refreshes a `release/next` branch carrying the version bump, the
  relocked `uv.lock`, and the `## Unreleased` section retitled to the version
  being cut; merging that pull request is the release, and a second workflow
  tags the merge commit. The bump therefore passes the ordinary gate as a
  reviewed change, so the commit that gets tagged is the commit CI tested, and
  no workflow pushes to `master`. The bump level comes from the Conventional
  Commits types since the last tag, and any commit whose type is unrecognised is
  reported rather than silently counted as a patch. Release mechanics live in
  `automation/ci/` — version arithmetic, commit reading, changelog promotion
  and the project file kept apart — and are driven by `invoke release-prepare`
  and `invoke release-notes` from `automation/ci/tasks/`, which the root
  `tasks.py` puts on the path. Keeping the automation outside `src/` means it
  is never packaged, so the wheel stays a single top-level `gaxi`. The changelog
  itself is still written by hand as work lands; releasing renames its section
  rather than deriving prose from commit subjects.
- Released gaxi as a Nix package: `packages/gaxi` builds the console script with
  `buildPythonApplication` against nixpkgs' Python 3.13 and gates on the offline
  suites (`tests/gaxi/{unit,properties}`), and the root `package.nix` maps it to
  `packages.default` so `nix build`, `nix run` and `nix flake check` work from a
  clean checkout. The runtime closure is the interpreter alone.
- Declared the project MIT: a `LICENSE` file, a PEP 639 `license`/`license-files`
  pair in `pyproject.toml` (which raises the build requirement to
  `setuptools>=77`), and `meta.license` on the Nix package. The wheel now carries
  `License-Expression: MIT` and ships the license text.
- Cut the flake down to what gaxi actually needs. `nixpkgs` was following
  `toolbox`, a private local flake, so nothing outside that machine could build
  the package and `nix develop` failed outright; the inputs are now `nixpkgs`
  (pinned to `nixos-26.05`) and `blueprint`, and the lock drops from 21 nodes to
  3. The devshell is a plain `mkShell` carrying the gaxi toolchain — Python
  3.13, uv, ruff, nixfmt, Node for pyright, git — in place of the borrowed
  trading-project shell and its IDE, `jsh`, and `ibkr-gateway` packages.
- Moved the `jsh` developer shell into its own flake at `dev/`, entered with
  `nix develop ./dev`. It still builds on the local `toolbox` flake and now
  carries gaxi's toolchain instead of the trading project's, but because it is a
  separate flake the root `nix build`, `nix flake check` and `nix flake show`
  never reach it and stay buildable without toolbox checked out.
- Made the executable-path tests name their home directory instead of reading
  it. They cleared the environment and then compared against `Path.home()`,
  which falls back to the account database once HOME is gone; the two agree on a
  developer machine but not in a Nix build sandbox, where HOME is
  `/homeless-shelter`.
- Added a `Nix package` job to the `check` workflow: it builds `.#gaxi` (whose
  check phase runs the offline suites), runs the installed console script, and
  evaluates every flake output with `nix flake check --no-build`.
- Fixed the built-in `Issue` and `PullRequest` projections: they named `index`,
  the Go struct field, where Gitea's JSON key is `number`. The identifier was
  silently filtered out of every issue and pull-request list default, leaving
  `{title,state,updated_at}` with nothing to address a detail request with, and
  `--fields index` failed validation. Default list output for both entities now
  begins with `number` (ADR 0001, ADR 0007).
- Renamed the bridge to `gaxi`: the console script, the import package, the
  `GAXI_*` environment variables, and the `.gaxi-cache` directory all change with
  no compatibility alias (ADR 0017).
- Raised the supported interpreter floor to Python 3.13 (ADR 0016).
- Replaced the Makefile and `scripts/` with the `python-codeforge` Invoke gate:
  `uv run invoke verify` runs the quality gates and the CLI-documentation
  freshness check (ADR 0016).
- Moved the suites to `tests/gaxi/{unit,properties,integration}` under pytest,
  with the live-instance suite marked `network`.
- Annotated the whole package and both suites; `mypy --strict` and `pyright` in
  strict mode pass (ADR 0018).
- Split `gaxi.capability`, `gaxi.results`, `gaxi.invocation`, and `gaxi.jsonbody`
  out of the modules that had accumulated them (ADR 0018).
- Renamed `GaxError` to `GaxiError`, completing the rename in ADR 0017.
- `--save` now streams a successful response straight to disk; the classifier no
  longer drains the body first (ADR 0018).
- Raised statement and branch coverage to 100% and removed four unreachable
  branches the coverage run exposed (ADR 0018).
- A path that carries an origin (`gaxi get https://host/api/v1/user`) is still
  refused, but the suggested command is now directly runnable: it drops the origin
  and, when the catalog is reachable, the instance base path too. Previously it
  prefixed a slash to whatever was typed.
- A path that repeats the instance base path (`/api/v1/user`) names that as the
  reason and suggests the capability it would have matched.

## 1.0.0

First implementation of the clean-sheet design.

- Hybrid capability model: Swagger 2.0 compilation, versioned semantic policy,
  runtime inspection, conservative fallback, and origin-scoped overlays.
- Verb commands (`get`, `post`, `put`, `patch`, `delete`) over concrete
  API-relative paths, with `--as`/`--operation` disambiguation.
- Schema-routed `name=value` input binding, `query:`/`body:`/`form:` qualifiers,
  repeated array assignments, file inputs, and `--input-json`.
- Independent `effect`, `confirmation`, and `retry` properties; `--yes`,
  `--allow-unknown`, and `--dry-run`; no interactive prompts.
- Content-first TOON results with `--output json|yaml`, a 160-character
  truncation contract, `--fields`, `--full`, and bounded pagination defaults.
- Explicit transport modes: structured text, `--raw`, `--save` with atomic
  rename and a receipt, bounded GET redirects, and refused mutation redirects.
- Discovery surface: live home view, `capabilities`, `capability`, `context`,
  `skill`, `setup`, and `auth`.
