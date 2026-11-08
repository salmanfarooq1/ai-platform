# Grafana state transition

The observability profile uses Grafana 13.2.4 distroless-slim. Its configured Prometheus datasource and provisioned Platform trust dashboard are supported. The local image omits optional bundled plugins. Existing custom plugins require a separate compatibility and security check.

Fresh installations use `grafana_data_v13`. The previous `grafana_data` volume remains untouched. Do not start the new image over that original volume: Grafana applies database migrations, and older versions cannot safely read the migrated state.

For an existing installation:

1. Stop Grafana and prevent further writes. Record the previous image digest. Back up the entire stopped data volume, including its SQLite database, plugins and other state. Preserve provisioning files and required configuration or secrets separately, without writing them to logs.
2. Keep the original volume and backup unchanged. Restore or clone the stopped data into `grafana_data_v13`, retaining the ownership expected by the container. For an external database, use that database's supported backup/restore process into a separate candidate database instead.
3. Start the candidate against the new volume. Check health, existing saved dashboard identities/content, users and permissions, datasource queries, installed plugins and the provisioned Platform trust dashboard. Switch to the candidate only after those checks pass.
4. Keep the old deployment and original state available until the transition is accepted. Verify that the stopped backup restores successfully using the previous image.

Before writes resume, rollback uses the old image and the unchanged original volume. After writes resume, the old state lacks subsequent changes; reconcile them through a reviewed recovery procedure. Never run an older Grafana image directly against the migrated database. Do not delete either volume during the transition.

The automated upgrade smoke check covers the previous Grafana 12.0.2 local stack, a saved dashboard, provisioning, and restoration of the stopped old-state snapshot. It does not establish compatibility for every external authentication provider, plugin or database; existing installations verify those integrations before switching.
