EXPECTATION_TO_STYLE = {
    "acceptance": "supportive",
    "reasons": "deep",
    "cope": "practical",
    "patterns": "behavior",
    "thoughts": "cbt",
    "unknown": "universal",
}


BUDGET_LIMITS = {
    "under_2000": 2000,
    "2000_3000": 3000,
    "3000_5000": 5000,
    "5000_plus": 100000,
    "not_important": 100000,
}


def calculate_match_score(psychologist: dict, answers: dict) -> int:
    score = 0

    requests = answers.get("requests") or ([answers.get("request")] if answers.get("request") else [])
    expectations = answers.get("expectations") or ([answers.get("expectation")] if answers.get("expectation") else [])
    therapy_experience = answers.get("therapy_experience")
    preferred_gender = answers.get("preferred_gender")
    budget = answers.get("budget")
    start_time = answers.get("start_time")
    priorities = answers.get("priorities", [])

    matched_topics = set(requests) & set(psychologist.get("help_topics", []))
    score += min(35, 12 * len(matched_topics))

    expected_styles = {EXPECTATION_TO_STYLE.get(item) for item in expectations}
    expected_styles.discard(None)
    matched_styles = expected_styles & set(psychologist.get("styles", []))
    score += min(20, 10 * len(matched_styles))

    if therapy_experience in psychologist.get("therapy_experience_fit", []):
        score += 5

    if preferred_gender == "any":
        score += 10
    elif preferred_gender == psychologist.get("gender"):
        score += 10

    if budget:
        budget_limit = BUDGET_LIMITS.get(budget, 100000)
        cheapest = psychologist.get("min_price")
        if cheapest is not None and cheapest <= budget_limit:
            score += 15

    if psychologist.get("slots"):
        score += 10

    if "request" in priorities and matched_topics:
        score += 10

    if "price" in priorities and budget:
        budget_limit = BUDGET_LIMITS.get(budget, 100000)
        cheapest = psychologist.get("min_price")
        if cheapest is not None and cheapest <= budget_limit:
            score += 10

    if "time" in priorities and psychologist.get("slots"):
        score += 10

    if "gender" in priorities:
        if preferred_gender == "any" or preferred_gender == psychologist.get("gender"):
            score += 5

    if "experience" in priorities:
        if psychologist.get("experience_years", 0) >= 5:
            score += 5

    if "style" in priorities and matched_styles:
        score += 5

    if "duration" in priorities and psychologist.get("durations"):
        score += 5

    if start_time in ["today", "week"] and psychologist.get("slots"):
        score += 5

    return score


def get_ranked_psychologists(answers: dict, psychologists: list[dict]) -> list[dict]:
    ranked = []

    for psychologist in psychologists:
        score = calculate_match_score(psychologist, answers)
        item = psychologist.copy()
        item["match_score"] = score
        ranked.append(item)

    ranked.sort(key=lambda x: x["match_score"], reverse=True)
    return ranked
