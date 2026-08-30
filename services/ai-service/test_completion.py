import os
from groq import Groq

# Load the env file manually if needed
try:
    with open("../../.env") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                key, val = line.strip().split("=", 1)
                os.environ[key] = val
except Exception:
    pass

api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)

models_to_test = [
    "groq/compound",
    "groq/compound-mini",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b"
]

for model in models_to_test:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello, answer in one word."}],
            max_tokens=10
        )
        print(f"SUCCESS {model}: {response.choices[0].message.content}")
    except Exception as e:
        print(f"FAILED {model}: {e}")
