# Agent instructions

This repository follows [AXI (Agent eXperience Interface)](https://axi.md): token budget, task success, and round-trip count are first-class design constraints. Treat this file as the implementation and review contract for AXI compliance. Apply the principles to the repository’s own domain, commands, and output formats.

## AXI contract

Every user-visible command should satisfy these rules unless the command is an explicitly documented exception:

1. **Token-efficient output.** Use TOON as the default structured format where the interface emits structured data. Keep output compact, deterministic, and easy to pipe. Route list output through a shared printer when one exists; do not invent command-specific table formats. JSON/YAML may be explicit opt-in formats.
2. **Minimal default schemas.** List commands return only 3–4 useful fields by default, normally an identifier plus title/name and state/status. Do not put `body`, comments, descriptions, URLs, nested users, or other verbose fields in list defaults. Expose additional fields through `--fields`.
3. **Content truncation.** Truncate long strings in list and summary output at a documented/shared limit. Include a size hint and tell the caller how to retrieve the complete value. Detail commands must provide `--full` (or an equivalent explicit escape hatch) to disable truncation.
4. **Pre-computed aggregates.** Report totals before collection data, for example `count: N of M total`, where `N` is the returned page size and `M` is the server total. Include useful domain-specific derived state inline when it avoids a follow-up request.
5. **Definitive empty states.** A successful empty result is never silent. Emit `count: 0` and a named typed empty collection, such as `issues[0]{id,title,state}:`.
6. **Structured errors and exit codes.** Emit machine-readable errors on stdout, including at least an error message and relevant status/operation context. Reserve stderr for debug, trace, and incidental diagnostics. Successful commands exit 0; ordinary failures exit 1; unknown commands or flags fail loudly with exit 2. Never silently ignore an invented flag. Mutations must be idempotent where possible and must never require an interactive prompt. Destructive mutations require an explicit confirmation flag appropriate to the project (for example, `-y`/`--yes`), especially when stdin is not a TTY.
7. **Ambient context.** Provide an explicit setup path for opt-in session context (hooks/plugin integration) and an on-demand Agent Skill generated from the same guidance. The session context should be compact, scoped to the current directory/repository, and available before an agent acts.
8. **Content first.** No-argument entry points show live, actionable state, not usage text. The home view includes the executable path (using `~` for the home-directory prefix), a one-sentence description, and a compact useful data view. Entity nouns should default to their list operation where that is unambiguous.
9. **Contextual disclosure.** Append `help[N]:` suggestions after successful and relevant empty/error output. Suggestions must be concrete command templates for the next likely steps, carry forward fixed disambiguating flags, and use placeholders such as `<id>` for runtime values—never guessed IDs. Keep the list short (normally 1–3 suggestions).
10. **Consistent help.** Every subcommand supports a concise `--help` fallback. Help must describe actual flags, defaults, output shape, and examples without dumping large schemas. Generate checked-in CLI documentation with `uv run invoke docs`.

## Output invariants

Before adding or changing a command, answer these questions in its tests and implementation:

- What is the default TOON entity name and ≤4-field schema?
- How are `--fields`, `--full`, pagination, and explicit output formats handled?
- What exact `count:` line appears for non-empty and empty results?
- What does a structured failure look like, and does it use the right exit code?
- What 1–3 `help[]` commands can the caller run next?
- Which operations are destructive, and how is `--yes` enforced non-interactively?
- Does no-args behavior expose useful live data rather than help?

Use stable field ordering and stable headers. Do not make agents infer whether empty stdout means “no results”, “a failed command”, or “a missing field”. Do not require an agent to make a second request for totals or obvious derived status when the API already exposes enough information to compute them.

## Repository integration

| Concern | Location |
|---|---|
| Commands and flags | Project’s command/interface modules |
| Output and TOON | Project’s shared output/printer modules |
| Default output format | Project’s output configuration |
| CLI/API documentation | Project’s documentation and generation targets |
| Agent usage guidance | Project’s skill or agent-instructions directory |
| AXI rationale | [axi.md](https://axi.md), plus any local AXI documentation |

Names and paths above are roles, not required directory names. Discover the repository’s actual equivalents before making changes. When a referenced implementation or document is absent, do not fabricate its status; record the gap and keep new guidance self-contained.

## Change checklist

For every command or output change:

1. Inspect shared output/flag helpers before adding local behavior.
2. Add or update TOON shape tests, including non-empty and empty results.
3. Test truncation, `--full`, `--fields`, aggregates, structured errors, exit codes, and non-interactive destructive-operation safety as applicable.
4. Add `help[]` suggestions and verify placeholders do not contain guessed runtime values.
5. Update generated docs and changelog when a default schema or output shape changes; narrowing default `--fields` is a behavior change.
6. Run the repository quality gates before handoff:

   ```bash
   uv run invoke verify
   ```

New list commands should use the project’s shared field/flag helpers when those helpers exist, and should share the common structured-output printer.
