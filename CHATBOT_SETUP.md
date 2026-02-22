# 🤖 AI Chatbot Assistant Setup Guide

Your nutrition app now includes a personalized AI assistant powered by OpenRouter! Here's how to set it up:

## 🚀 Quick Setup

### 1. Get OpenRouter API Key
1. Visit [https://openrouter.ai/keys](https://openrouter.ai/keys)
2. Sign up or log in to your account
3. Create a new API key
4. Copy the key (starts with `sk-or-v1-...`)

### 2. Configure Environment
1. Open the `.env` file in your project root
2. Replace `your_openrouter_api_key_here` with your actual API key:
   ```
   OPENROUTER_API_KEY=sk-or-v1-your-actual-key-here
   ```
3. Save the file

### 3. Install Dependencies
Run the following command to install the new dependencies:
```bash
pip install -e .
```
or if using uv:
```bash
uv sync
```

## ✨ Features

Your AI assistant can:
- **Personalized Conversations**: Addresses you by name and knows your goals
- **Progress Analysis**: Discusses your weight trends and achievements  
- **Meal Suggestions**: Recommends foods based on your macro targets
- **Troubleshooting**: Helps solve plateau issues or consistency problems
- **Motivation**: Provides encouragement tailored to your journey
- **Education**: Explains how the adaptive calorie system works

## 🎯 How to Use

### Chat Location
- The assistant appears in the **bottom of the left sidebar**
- Available on all pages when you're logged in

### Quick Start Topics
The assistant suggests conversation starters based on your current situation:
- "How am I progressing toward my goal?"
- "Suggest meals for my macro targets"  
- "I need some motivation"
- "Explain how the adaptive system works"

### Smart Context
The assistant knows:
- Your current weight and goals
- Recent food entries and patterns
- Goal adaptations and reasons
- Data consistency insights
- Your specific challenges and wins

## 🛠️ Troubleshooting

### "Assistant unavailable" Error
- Check that your API key is correctly set in `.env`
- Ensure you have internet connectivity
- Verify your OpenRouter account has credits (the free model has limits)

### Slow Responses
- The free Llama model may have usage limits
- Consider upgrading to a paid OpenRouter plan for faster responses

### Chat Not Appearing
- Make sure you're logged in as a user
- Check that dependencies are installed (`requests`, `python-dotenv`)
- Restart the Streamlit app after adding the API key

## 💡 Cost Information

- **Free Model**: `meta-llama/llama-3.3-70b-instruct:free`
- OpenRouter provides free credits for new users
- Monitor usage at [https://openrouter.ai/activity](https://openrouter.ai/activity)

## 🔒 Privacy & Security

- Your API key stays local in your `.env` file
- Conversations are not stored permanently (only in session)
- Only your progress data is shared with the AI for personalization
- No sensitive personal information is transmitted

---

**Ready to chat with your AI nutrition coach? Set up your API key and start your conversation!** 🚀