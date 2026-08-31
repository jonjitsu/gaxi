# Discover instance context from Git

Without an explicit server setting, the bridge will derive the instance origin, owner, and repository from the current Git repository's remote before considering a configured default. The remote is useful ambient context but not a credential source: inferred origins are probed anonymously, and stored credentials are sent only for an exact previously trusted origin match; ambiguous SSH-to-web mappings require configuration rather than an insecure guess.
