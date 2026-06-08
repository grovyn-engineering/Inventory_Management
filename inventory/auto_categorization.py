import re
from collections import Counter

from .models import Category, CategoryCorrection

TOKEN_SPLIT_PATTERN = re.compile(r"[^a-z0-9]+")
STOPWORDS = {
    "and",
    "for",
    "with",
    "the",
    "pack",
    "pcs",
    "piece",
    "new",
    "premium",
    "best",
    "fresh",
    "original",
    "set",
}

RULE_KEYWORDS = {
    "tablet": "Tablets",
    "coffee": "Beverages",
    "shirt": "Clothing",
}

ML_KEYWORD_WEIGHTS = {
    "beverage": {"coffee": 0.7, "tea": 0.6, "juice": 0.6, "drink": 0.5},
    "tablets": {"tablet": 0.8, "pill": 0.7, "capsule": 0.6},
    "clothing": {"shirt": 0.8, "tshirt": 0.7, "jeans": 0.7, "pant": 0.6},
    "electronics": {"phone": 0.8, "laptop": 0.8, "charger": 0.6, "headphone": 0.6},
    "grocery": {"rice": 0.6, "flour": 0.6, "oil": 0.6, "salt": 0.5},
}


def normalize_product_name(name):
    raw = (name or "").lower().strip()
    cleaned = TOKEN_SPLIT_PATTERN.sub(" ", raw)
    return " ".join(cleaned.split())


def extract_keywords(name):
    normalized = normalize_product_name(name)
    if not normalized:
        return []
    tokens = [token for token in normalized.split(" ") if token and token not in STOPWORDS]
    return tokens


def _resolve_category_by_name(name, *, fallback=False):
    if not name:
        return None
    category = Category.objects.filter(name__iexact=name, is_active=True).first()
    if category:
        return category
    if not fallback:
        return None
    category, _ = Category.objects.get_or_create(
        name=name,
        defaults={"is_active": True},
    )
    return category


def _predict_from_corrections(normalized_name):
    if not normalized_name:
        return None, 0.0
    corrections = CategoryCorrection.objects.filter(
        normalized_name=normalized_name
    ).select_related("selected_category")
    if not corrections.exists():
        return None, 0.0

    counts = Counter(
        correction.selected_category.name.lower()
        for correction in corrections
        if correction.selected_category and correction.selected_category.is_active
    )
    if not counts:
        return None, 0.0
    best_name, count = counts.most_common(1)[0]
    total = sum(counts.values())
    category = _resolve_category_by_name(best_name)
    confidence = min(0.99, 0.6 + (count / max(total, 1)) * 0.35)
    return category, round(confidence, 3)


def predict_category_ml(name):
    normalized_name = normalize_product_name(name)
    category, confidence = _predict_from_corrections(normalized_name)
    if category:
        return category, confidence, "ml-learning"

    keywords = extract_keywords(normalized_name)
    if not keywords:
        return None, 0.0, "ml"

    scores = {}
    for token in keywords:
        for category_name, keyword_weights in ML_KEYWORD_WEIGHTS.items():
            if token in keyword_weights:
                scores[category_name] = scores.get(category_name, 0) + keyword_weights[token]

    if not scores:
        return None, 0.0, "ml"

    winner = max(scores, key=scores.get)
    confidence = min(0.95, max(0.35, scores[winner] / max(len(keywords), 1)))
    category = _resolve_category_by_name(winner, fallback=True)
    return category, round(confidence, 3), "ml"


def apply_rule_override(name, ml_category=None):
    keywords = extract_keywords(name)
    for token in keywords:
        rule_category_name = RULE_KEYWORDS.get(token)
        if rule_category_name:
            category = _resolve_category_by_name(rule_category_name, fallback=True)
            return category, 0.98, "rules"
    if ml_category:
        return ml_category, None, "ml"
    return None, 0.0, "rules"


def suggest_category(name):
    normalized_name = normalize_product_name(name)
    keywords = extract_keywords(name)
    ml_category, ml_confidence, ml_source = predict_category_ml(normalized_name)
    rule_category, rule_confidence, source = apply_rule_override(normalized_name, ml_category)

    chosen = rule_category or ml_category
    confidence = rule_confidence if source == "rules" else ml_confidence
    if not chosen:
        chosen, _ = Category.objects.get_or_create(
            name="Uncategorized",
            defaults={"is_active": True},
        )
        confidence = 0.2
        source = "fallback"

    return {
        "category": chosen,
        "confidence": round(confidence or 0.0, 3),
        "source": source if source != "ml" else ml_source,
        "normalized_name": normalized_name,
        "keywords": keywords,
    }


def record_category_override(*, name, predicted_category, selected_category, created_by=None):
    normalized_name = normalize_product_name(name)
    if not normalized_name or not selected_category:
        return None
    predicted_id = predicted_category.id if predicted_category else None
    if predicted_id == selected_category.id:
        return None
    return CategoryCorrection.objects.create(
        normalized_name=normalized_name,
        predicted_category=predicted_category,
        selected_category=selected_category,
        created_by=created_by,
    )
