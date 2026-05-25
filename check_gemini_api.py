#!/usr/bin/env python
"""Check available models with the given API key."""

import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"services\ai_service\.env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
print(f"API Key loaded: {GEMINI_API_KEY[:20]}..." if GEMINI_API_KEY else "No API key found")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    
    print("\n🔍 Attempting to list available models...\n")
    try:
        models = genai.list_models()
        for model in models:
            print(f"📌 {model.name}")
            print(f"   Display Name: {model.display_name}")
            print(f"   Generation Methods: {model.supported_generation_methods}")
            print()
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nTrying direct test with gemini-pro...")
        try:
            model = genai.GenerativeModel("gemini-pro")
            response = model.generate_content("Hello")
            print("✅ gemini-pro works!")
            print(f"Response: {response.text[:100]}")
        except Exception as e2:
            print(f"❌ gemini-pro failed: {e2}")
