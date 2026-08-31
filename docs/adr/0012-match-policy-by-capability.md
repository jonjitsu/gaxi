# Match semantic policy by capability

Semantic policy will ship with the CLI and match the connected instance primarily by method/path capability plus optional schema fingerprints, rather than selecting one monolithic policy from the reported Gitea version. Strict version gating was rejected because patched and newer instances can retain compatible capabilities; unknown shapes fall back conservatively, and no server-provided policy is trusted automatically.
