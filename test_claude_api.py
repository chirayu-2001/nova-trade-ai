import os
from dotenv import load_dotenv
import anthropic

def main():
    print("Loading .env file...")
    load_dotenv()
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in environment variables.")
        return
        
    print(f"Found API Key starting with: {api_key[:15]}...")
    
    try:
        print("Initializing Anthropic client...")
        client = anthropic.Anthropic(api_key=api_key)
        
        print("Sending test request to Claude...")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Hello, this is a test. Please reply with 'API is working!'"}
            ]
        )
        
        print("\n✅ SUCCESS! API is working.")
        print("Claude replied:", response.content[0].text)
        
    except anthropic.AuthenticationError as e:
        print("\n❌ AUTHENTICATION ERROR: Your API key is invalid.")
        print(f"Details: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
