from app.detection.isolation_forest import normalize_raw_score
from sklearn.metrics import f1_score, precision_score, recall_score


def main() -> None:
    # Reproducible toy evaluation for demo reporting. Real claims require larger labeled data.
    y_true = [0, 0, 0, 0, 1, 1, 1]
    scores = [0.05, 0.12, 0.22, 0.31, 0.72, 0.84, 0.91]
    y_pred = [1 if score >= 0.7 else 0 for score in scores]
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    fp = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == 0 and pred == 1)
    tn = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == 0 and pred == 0)
    print(
        {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "false_positive_rate": round(fp / max(fp + tn, 1), 3),
            "preliminary": True,
            "normalized_example": normalize_raw_score(-0.1),
        }
    )


if __name__ == "__main__":
    main()
