#!/usr/bin/env python
"""Check available Gemini models."""

import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=GEMINI_API_KEY)

print("Available models:")
for model in genai.list_models():
    print(f"  - {model.name}")
    if "generateContent" in model.supported_generation_methods:
        print(f"    ✓ Supports generateContent")
