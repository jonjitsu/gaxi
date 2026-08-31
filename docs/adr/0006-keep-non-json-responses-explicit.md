# Keep non-JSON responses explicit

Text and HTML responses will remain structured and bounded by default, while exact content requires `--raw` and binary content requires `--save` or `--raw`. Successful raw output is a documented structured-output exception; saved files produce a structured receipt, cross-origin redirects drop credentials, and existing files are never replaced without `--overwrite`.
