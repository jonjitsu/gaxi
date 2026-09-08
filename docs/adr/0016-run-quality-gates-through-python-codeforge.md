# Run quality gates through python-codeforge

The repository's gates are the reusable Invoke tasks published as
`python-codeforge`, pinned in the `dev` dependency group to the published release
wheel for `1.1.0` and exposed through a two-line `tasks.py`. The pin is a
`[tool.uv.sources]` URL rather than a Git tag because a wheel is an immutable
artefact `uv.lock` can hash, which keeps `uv export` hashed and lets a strict
dependency audit cover the gate's own tree. `uv run invoke verify` is the gate:
Codeforge's `check` (hygiene, lint, strict typing, dead code, maintainability,
cognitive complexity, tests, per-package coverage, CRAP) followed by this
project's documentation-freshness task. The Makefile and the `scripts/` directory are removed.

A loose shell script is unimported, so it is untyped, untested, and uncallable from
another task; the two scripts it replaced duplicated logic that the shared tasks
already own. Keeping automation in an installed package means the gate is itself
type-checked and unit-tested, and that this repository and its siblings drift apart
only where they configure different thresholds rather than where they wrote
different shell. The documentation check stays local because it is specific to
`gaxi.docsgen`: it is a project task added to the imported namespace, and it shells
out to the generator rather than importing it, so automation never depends on the
product's internals.

The interpreter floor moves to 3.13, which the toolchain requires. Nothing in the
package needed the previous 3.11 floor — the sources parse under 3.8 grammar and use
no standard-library API newer than 3.9 — and no job ever tested a second version, so
the earlier floor was an untested promise rather than a measured constraint. The
runtime dependency set is unchanged: `gaxi` still installs with no dependencies
outside the standard library, and Codeforge is a development-only dependency that
never reaches an installed bridge.

Test layout follows the package-then-kind partition the tasks assume:
`tests/gaxi/unit`, `tests/gaxi/properties`, and `tests/gaxi/integration` for the
live-instance suite, which carries the `network` marker. `tests/conftest.py` holds
Hypothesis profiles and nothing else.
