import os
import requests
import json
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class OpenRouterClient:
    """Client for interacting with OpenRouter API using Llama 3.3 70B Instruct model"""
    
    def __init__(self):
        self.api_key = os.environ.get('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "nvidia/nemotron-3-nano-30b-a3b:free"
        
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not found in environment variables. "
                "Please create a .env file with your OpenRouter API key."
            )
    
    def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        max_tokens: int = 1000,
        temperature: float = 0.7,
        stream: bool = False
    ) -> Dict:
        """Send chat completion request to OpenRouter API"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",  # Streamlit default port
            "X-Title": "Adaptive Nutrition Tracker"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        try:
            response = requests.post(
                self.base_url, 
                headers=headers, 
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            return {
                "error": f"API request failed: {str(e)}",
                "choices": [{
                    "message": {
                        "content": "I'm having trouble connecting to my AI service right now. Please try again in a moment. 🤖"
                    }
                }]
            }
        except json.JSONDecodeError as e:
            return {
                "error": f"Invalid JSON response: {str(e)}",
                "choices": [{
                    "message": {
                        "content": "I received an unexpected response. Please try again. 🔄"
                    }
                }]
            }
    
    def test_connection(self) -> bool:
        """Test if the API connection is working"""
        test_messages = [
            {"role": "user", "content": "Hello, please respond with just 'OK' if you can hear me."}
        ]
        
        response = self.chat_completion(test_messages)
        return "error" not in response and len(response.get("choices", [])) > 0
