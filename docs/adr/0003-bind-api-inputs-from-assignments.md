# Bind API inputs from assignments

API inputs will use schema-routed `name=value` assignments after the concrete path, while `--flags` are reserved for bridge controls. Generating an option flag for every Swagger parameter was rejected because API names can collide with stable bridge options; full JSON remains available for complex bodies, and location-qualified assignments resolve the uncommon case where one capability declares the same name in multiple locations.
