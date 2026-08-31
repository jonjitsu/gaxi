# Model execution properties independently

Semantic policy will describe each capability with independent effect, confirmation, and retry properties rather than a single risk class. Known destructive mutations require `--yes`, unknown mutation semantics require `--allow-unknown`, and only operations explicitly known to be retry-safe may be retried automatically; this keeps confirmation meaningful for an agent instead of encouraging it to append `--yes` to every write.
