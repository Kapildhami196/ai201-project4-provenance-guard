from services.llm_detector import LlmDetectionError, analyze_text


sample_text = """
Artificial intelligence represents a transformative paradigm shift in modern
society. It is important to note that while the benefits of AI are numerous,
it is equally essential to consider the ethical implications. Furthermore,
stakeholders across various sectors must collaborate to ensure responsible deployment.
""".strip()


try:
    result = analyze_text(sample_text)
    print("Groq detector succeeded")
    print("LLM score:", result["llm_score"])
    print("Reasoning:", result["reasoning"])
    print("Model:", result["model"])
except LlmDetectionError as error:
    print("Groq detector failed:", error)
