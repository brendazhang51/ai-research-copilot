import os
from openai import OpenAI
from .schemas import AnalysisPlan

SYSTEM_PROMPT = """
You are a senior biostatistician and clinical epidemiologist.

Given a research question, produce a rigorous, SAP-style analysis plan.
Be concrete and clinically plausible.

Return structured output that strictly follows the provided schema.
"""

def build_user_prompt(question: str, context: str | None = None) -> str:
    if context:
        return f"Question: {question}\nContext: {context}"
    return f"Question: {question}"

def generate_plan(question: str, context: str | None = None) -> AnalysisPlan:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found in environment variables.")

    client = OpenAI(api_key=api_key)

    user_content = build_user_prompt(question, context)

    result = client.responses.parse(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
        text_format=AnalysisPlan,
    )

    return result.output_parsed