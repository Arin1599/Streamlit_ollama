import streamlit as st
import ollama
import json
from typing import Iterator
from PIL import Image
import io
import uuid
from datetime import datetime
from db_utils import ChatDatabase

# Disable Streamlit's file watcher
import os
os.environ['STREAMLIT_SERVER_FILE_WATCHER'] = 'false'

# Initialize database
db = ChatDatabase()

def generate_unique_chat_id():
    return str(uuid.uuid4())

def build_context(recent_messages, current_prompt):
    context = "Previous conversation:\n"
    for role, content in recent_messages:
        context += f"{role}: {content}\n"
    context += f"\nCurrent question: {current_prompt}\n"
    return context

def get_local_models():
    try:
        models = ollama.list()
        return [model.model for model in models.models]
    except Exception as e:
        st.error(e)
        return []

def stream_chat(model: str, message: str, temperature: float, chat_id: str, image=None) -> Iterator[str]:
    try:
        options = {
            "temperature": temperature,
        }
        
        relevant_messages = db.get_relevant_context(message, chat_id)
        context_prompt = build_context(relevant_messages, message)
        
        if image:
            stream = ollama.generate(
                model=model,
                prompt=context_prompt,
                images=[image],
                options=options,
                stream=True
            )
        else:
            stream = ollama.generate(
                model=model,
                prompt=context_prompt,
                options=options,
                stream=True
            )
        
        for chunk in stream:
            if 'response' in chunk:
                yield chunk['response']
    except Exception as e:
        st.error(f"Error communicating with Ollama: {str(e)}")
        yield ""

def load_chat_history(chat_id):
    """
    Load complete chat history and convert to message format
    """
    history = db.get_chat_history(chat_id)
    messages = []
    for role, content, image, timestamp in history:
        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp
        }
        if image is not None:
            message["image"] = image
        messages.append(message)
    return messages

# Streamlit UI
st.title("Chat with Local Ollama Models")

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'chat_id' not in st.session_state:
    st.session_state.chat_id = generate_unique_chat_id()

# Sidebar for model selection and temperature
with st.sidebar:
    st.write("## Chat Controls")
    if st.button("New Chat"):
        st.session_state.chat_id = generate_unique_chat_id()
        st.session_state.messages = []
        st.rerun()
    
    st.write("## Current Chat")
    st.code(st.session_state.chat_id, language=None)
    
    st.write("## Chat History")
    # Create a container for scrollable chat history
    with st.container():
        st.write("Click a chat to load its history:")
        chat_histories = db.get_all_chat_ids()
        
        for chat_id, timestamp, first_message in chat_histories:
            # Format the timestamp
            dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            formatted_time = dt.strftime('%Y-%m-%d %H:%M')
            
            # Truncate first message if too long
            preview = (first_message[:47] + '...') if len(first_message) > 50 else first_message
            
            # Create a clickable button for each chat
            button_label = f"📝 {formatted_time}\n{preview}"
            if st.button(button_label, key=chat_id):
                st.session_state.chat_id = chat_id
                st.session_state.messages = load_chat_history(chat_id)
                st.session_state.selected_chat = chat_id
                st.rerun()
    
    st.write("## Model Settings")
    models = get_local_models()
    if not models:
        st.error("No models found. Please ensure Ollama is running and models are installed.")
    selected_model = st.selectbox("Select Model", models if models else ["No models available"])
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.1)

# Display chat history
if st.session_state.messages:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if "image" in message and message["image"] is not None:
                st.image(message["image"])
            st.markdown(message["content"])
else:
    st.write("No messages in this chat yet. Start a conversation!")

# Image upload
uploaded_image = st.file_uploader("Upload an image (optional)", type=["jpg", "jpeg", "png"])
if uploaded_image:
    st.image(uploaded_image, caption="Uploaded Image")

# Chat input
if prompt := st.chat_input("What would you like to ask?"):
    # Display user message
    with st.chat_message("user"):
        if uploaded_image:
            st.image(uploaded_image)
        st.markdown(prompt)
    
    # Store user message in database
    image_bytes = uploaded_image.getvalue() if uploaded_image else None
    db.store_message(st.session_state.chat_id, "user", prompt, selected_model, image_bytes)
    
    message_data = {
        "role": "user",
        "content": prompt,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    if uploaded_image:
        message_data["image"] = image_bytes
    st.session_state.messages.append(message_data)

    # Display assistant response with streaming
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        for response_chunk in stream_chat(selected_model, prompt, temperature, st.session_state.chat_id, image_bytes if uploaded_image else None):
            if response_chunk:
                full_response += response_chunk
                message_placeholder.markdown(full_response + "▌")
        
        if full_response:
            message_placeholder.markdown(full_response)
            # Store assistant's response in database
            db.store_message(st.session_state.chat_id, "assistant", full_response, selected_model)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        else:
            st.error("No response received from the model. Please check if Ollama is running correctly.")