# Use one explicit truncation contract

Projected strings will be truncated at 160 Unicode characters by default, with an ellipsis, original character count, and an executable `--full` retrieval suggestion. Separate list/detail limits were rejected because they make output cost harder to predict; identifiers and control metadata remain lossless, while `--full` affects only selected content and never expands fields, pagination, or output format.
