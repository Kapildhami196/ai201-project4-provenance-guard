from services.scoring import combine_signals


test_cases = [
    {
        "name": "Strong AI agreement",
        "llm_score": 0.95,
        "stylometric_score": 0.90,
    },
    {
        "name": "Strong human agreement",
        "llm_score": 0.05,
        "stylometric_score": 0.10,
    },
    {
        "name": "Signals disagree",
        "llm_score": 0.90,
        "stylometric_score": 0.10,
    },
    {
        "name": "Both signals are near uncertain",
        "llm_score": 0.60,
        "stylometric_score": 0.55,
    },
]


for test_case in test_cases:
    result = combine_signals(
        test_case["llm_score"],
        test_case["stylometric_score"],
    )

    print()
    print(test_case["name"])
    print("LLM score:", test_case["llm_score"])
    print("Stylometric score:", test_case["stylometric_score"])
    print("AI probability:", result["ai_probability"])
    print("Signal agreement:", result["signal_agreement"])
    print("Confidence:", result["confidence"])
    print("Label:", result["label"]["title"])
