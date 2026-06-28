from services.stylometric_detector import (
    StylometricDetectionError,
    analyze_text,
)


sample_text = """
Artificial intelligence represents a transformative paradigm shift in modern
society. It is important to note that the benefits of AI are substantial.
Furthermore, stakeholders across various sectors must be considered carefully.
In conclusion, ethical implications should guide responsible deployment.
""".strip()


try:
    result = analyze_text(sample_text)

    print("Stylometric detector succeeded")
    print("Stylometric score:", result["stylometric_score"])
    print("Reasoning:", result["reasoning"])
    print("Method:", result["method"])
    print("Metrics:", result["metrics"])
except StylometricDetectionError as error:
    print("Stylometric detector failed:", error)
