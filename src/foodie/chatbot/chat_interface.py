import streamlit as st
from typing import Dict, List, Optional
from datetime import datetime
from foodie.logic.models import User
from .assistant import NutritionAssistant

def initialize_chat_state():
    """Initialize chat-related session state variables"""
    if 'chat_messages' not in st.session_state:
        st.session_state.chat_messages = []
    if 'chat_assistant' not in st.session_state:
        st.session_state.chat_assistant = NutritionAssistant()
    if 'chat_initialized' not in st.session_state:
        st.session_state.chat_initialized = False

def render_chat_assistant(user: User) -> None:
    """Render the chat assistant interface in the sidebar"""
    
    # Initialize chat state
    initialize_chat_state()
    
    # Chat container in sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 Your AI Assistant")
    
    # Test API connection on first load
    if not st.session_state.chat_initialized:
        with st.sidebar:
            with st.spinner("Connecting to AI assistant..."):
                try:
                    if st.session_state.chat_assistant.client.test_connection():
                        # Add greeting message
                        greeting = st.session_state.chat_assistant.get_greeting(user)
                        st.session_state.chat_messages.append({
                            "role": "assistant",
                            "content": greeting,
                            "timestamp": datetime.now()
                        })
                        st.session_state.chat_initialized = True
                    else:
                        st.error(f"❌ Could not connect to AI assistant. Please check your API configuration.")
                        return
                except Exception as e:
                    st.error(f"❌ Assistant setup failed: {str(e)}")
                    return
    
    # Chat interface container
    with st.sidebar:
        # Chat history container with fixed height
        chat_container = st.container(height=400)
        
        with chat_container:
            # Display chat messages
            for message in st.session_state.chat_messages:
                if message["role"] == "user":
                    with st.chat_message("user"):
                        st.write(message["content"])
                else:
                    with st.chat_message("assistant"):
                        st.write(message["content"])
        
        # Quick suggestion buttons (only show if no conversation yet or last was assistant)
        if (len(st.session_state.chat_messages) <= 1 or 
            (st.session_state.chat_messages and st.session_state.chat_messages[-1]["role"] == "assistant")):
            
            st.markdown("**💡 Quick topics:**")
            suggestions = st.session_state.chat_assistant.suggest_topics(user)
            
            # Create columns for suggestion buttons
            cols = st.columns(2)
            for i, suggestion in enumerate(suggestions):
                col = cols[i % 2]
                suggestion_text = suggestion.split(' ', 1)[1] if ' ' in suggestion else suggestion
                
                if col.button(
                    suggestion_text, 
                    key=f"suggestion_{i}",
                    help=suggestion,
                    use_container_width=True
                ):
                    # Add user message
                    st.session_state.chat_messages.append({
                        "role": "user",
                        "content": suggestion_text,
                        "timestamp": datetime.now()
                    })
                    
                    # Get AI response
                    with st.spinner("Thinking..."):
                        # Prepare conversation history for context (exclude timestamps)
                        conversation_history = []
                        for msg in st.session_state.chat_messages[:-1]:  # Exclude the just-added message
                            if msg["role"] in ["user", "assistant"]:
                                conversation_history.append({
                                    "role": msg["role"],
                                    "content": msg["content"]
                                })
                        
                        ai_response = st.session_state.chat_assistant.chat(
                            suggestion_text, 
                            user, 
                            conversation_history
                        )
                    
                    # Add AI response
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": ai_response,
                        "timestamp": datetime.now()
                    })
                    st.rerun()
        
        # Chat input
        user_input = st.chat_input(
            placeholder="Ask me anything about your nutrition journey...",
            key="chat_input"
        )
        
        if user_input:
            # Add user message to chat
            st.session_state.chat_messages.append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now()
            })
            
            # Get AI response
            with st.spinner("Thinking..."):
                # Prepare conversation history for context
                conversation_history = []
                for msg in st.session_state.chat_messages[-6:-1]:  # Last 5 messages for context
                    if msg["role"] in ["user", "assistant"]:
                        conversation_history.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                
                ai_response = st.session_state.chat_assistant.chat(
                    user_input, 
                    user, 
                    conversation_history
                )
            
            # Add AI response to chat
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": datetime.now()
            })
            
            st.rerun()
        
        # Clear chat button
        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.chat_messages = []
            st.session_state.chat_initialized = False
            st.rerun()
        
        # API status indicator
        if st.session_state.chat_initialized:
            st.markdown("<div style='text-align: center; font-size: 12px; color: green;'>🟢 AI Assistant Ready</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='text-align: center; font-size: 12px; color: red;'>🔴 AI Assistant Disconnected</div>", unsafe_allow_html=True)
