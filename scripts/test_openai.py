#!/usr/bin/env python
"""
A simple script to test OpenAI API connectivity and model availability.
"""

import os
import sys
import openai
from dotenv import load_dotenv

def main():
    # Load environment variables
    load_dotenv()
    
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)
    
    print(f"Using OpenAI API key: {api_key[:5]}...{api_key[-4:]}")
    print(f"OpenAI Python package version: {openai.__version__}")
    
    try:
        # Initialize the client
        client = openai.Client(api_key=api_key)
        
        # List available models
        print("\nFetching available models...")
        models = client.models.list()
        
        print("\nAvailable models:")
        for model in models.data:
            print(f"- {model.id}")
        
        # Test a simple completion
        test_models = [
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0613",
            "gpt-4",
            "gpt-4-0613"
        ]
        
        print("\nTesting chat completions with different models:")
        for model_name in test_models:
            try:
                print(f"\nTesting model: {model_name}")
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Say hello!"}
                    ],
                    max_tokens=10
                )
                print(f"Response: {response.choices[0].message.content}")
                print(f"✅ Model {model_name} works!")
            except Exception as e:
                print(f"❌ Error with model {model_name}: {str(e)}")
        
        print("\nTest completed successfully!")
        
    except Exception as e:
        print(f"Error connecting to OpenAI API: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()