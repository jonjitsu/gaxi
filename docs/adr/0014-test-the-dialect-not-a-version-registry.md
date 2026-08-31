# Test the dialect, not a version registry

Compatibility tests will use small synthetic Swagger 2.0 feature documents, mock AXI response contracts, and dynamic compilation of every capability advertised by a configured live Gitea test instance. Maintaining full Swagger snapshots for several releases was rejected because it would turn tests into a version registry and recreate the per-release maintenance that live capability discovery is intended to remove.
