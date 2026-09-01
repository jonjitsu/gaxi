# Changelog

## Unreleased

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
