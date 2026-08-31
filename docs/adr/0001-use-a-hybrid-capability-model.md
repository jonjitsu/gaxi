# Use a hybrid capability model

The AXI bridge will treat each instance's Swagger definition as authoritative for available operations and transport, while a versioned Gitea semantic policy supplies AXI behavior that Swagger cannot reliably express. A schema-only bridge was rejected because the observed Gitea 1.27.2 definition omits usable success schemas for many operations and documents total-count headers for only a small fraction of paginated collections, while a fully curated client would lose instance-specific coverage.
