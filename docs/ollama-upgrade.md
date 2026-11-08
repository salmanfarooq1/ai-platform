# Local model runtime transition

The local model profile uses upstream Ollama 0.40.7, pinned by tag and digest in `docker-compose.yml`. Its image is scanned with the same fixed-critical gate as the other stack images. Runtime identity and scan evidence are in the Sprint 011 report.

Fresh installations use `ollama_data_v0407`. The original `ollama_data` remains untouched. The configured local service disables cloud inference and startup blob pruning. Its init job retains the existing embedding model; Sprint 013 adds verified model locks and actual model-inference checks.

For an existing installation, stop model downloads and writes using that store. Back up the complete stopped store and record its manifest/blob hashes. Clone it into a new volume, keeping the original volume and old image available. Pull the pinned runtime with `docker compose --profile models pull ollama ollama-pull`, then start it against the copy. Compare listed models and manifest/blob identities, and verify the models required by the deployment before switching clients. A named tag alone does not prove an unchanged model.

Do not attach the original volume to the new runtime or delete it as an upgrade step. Before new writes, rollback uses the original image/store. After downloads or modifications on the copy, reverting to the old store omits those changes; reconcile them explicitly. Never downgrade a modified store in place.

The isolated Sprint 011 smoke starts the rebuilt executable with networking disabled, lists its empty model store, checks version/build identity and measures idle memory. It makes no inference call and does not establish GPU support, loaded-model memory or compatibility for every existing model. Capture those deployment-specific checks before switching an existing installation.
