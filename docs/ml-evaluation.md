# ML Evaluation

The MVP uses Isolation Forest for unsupervised anomaly detection.

Training:

- Uses feature windows generated from simulated normal behavior.
- Uses deterministic random seeds.
- Saves artifacts to `models/`.
- Records metadata in `model_versions`.
- Trains device-type-specific baselines only when enough samples exist.

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

Current demo metrics are preliminary because the generated dataset is small.
