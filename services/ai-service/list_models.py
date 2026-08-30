import os
import sys
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
if not api_key:
    print("GROQ_API_KEY not found in environment or ../../.env")
    sys.exit(1)

client = Groq(api_key=api_key)
try:
    models = client.models.list()
    for model in models.data:
        print(f"- {model.id}")
except Exception as e:
    print(f"Error listing models: {e}")
