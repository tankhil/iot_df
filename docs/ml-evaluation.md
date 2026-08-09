# ML Evaluation

The MVP uses Isolation Forest for unsupervised anomaly detection.

Training:

- Uses feature windows generated from simulated normal behavior.
- Uses deterministic random seeds.
- Saves artifacts to `models/`.
- Records metadata in `model_versions`.
- Trains device-type-specific baselines only when enough samples exist.
- Computes a deterministic model identity fingerprint from model type, global or device-type scope, ordered feature schema and schema version, training-dataset hash, normalized hyperparameters, random seed, training-code version, and artifact format version.
- Reuses the same metadata row and artifact for identical fingerprints when the artifact is valid.
- Rebuilds a missing or corrupt artifact atomically for the same fingerprint without creating a duplicate row.
- Creates a new model version when the dataset, seed, schema, hyperparameters, model type, or training-code identity changes.

Inference:

- Produces normalized anomaly score from 0.0 to 1.0.
- Records model version with each detection.
- Falls back to safe non-anomalous output when no model exists.
- Never directly triggers quarantine.

Metrics prepared:

- Precision
- Recall
- F1 score
- False-positive rate
- Detection latency
- Response latency
- Quarantine accuracy
- Recovery success rate
- Simulated service downtime

Current demo metrics are preliminary because the generated dataset is small and synthetic. A synthetic F1 score of `1.0` is useful only as a smoke signal for the demo pipeline; it is not production evidence.
