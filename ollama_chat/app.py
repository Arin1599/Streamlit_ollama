import streamlit as st
import ollama
import json
from typing import Iterator
from PIL import Image
import io

# Disable Streamlit's file watcher
import os
os.environ['STREAMLIT_SERVER_FILE_WATCHER'] = 'false'


from db_utils import ChatDatabase

# Initialize database
db = ChatDatabase()

def build_context(recent_messages, current_prompt):
    context = "Previous conversation:\n"
    for role, content in recent_messages:
        context += f"{role}: {content}\n"
    context += f"\nCurrent question: {current_prompt}\n"
    return context

def get_local_models():
    try:
        models = ollama.list()
        print([model.model for model in models.models])
        return [model.model for model in models.models]
    except Exception as e:
        st.error(e)
        return []

def stream_chat(model: str, message: str, temperature: float, image=None) -> Iterator[str]:
    try:
        options = {
            "temperature": temperature,
        }
        
        # Get semantically relevant context
        relevant_messages = db.get_relevant_context(message)
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

# Streamlit UI
st.title("Chat with Local Ollama Models")

# Initialize session state
if 'messages' not in st.session_state:
    st.session_state.messages = []

# Sidebar for model selection and temperature
with st.sidebar:
    models = get_local_models()
    if not models:
        st.error("No models found. Please ensure Ollama is running and models are installed.")
    selected_model = st.selectbox("Select Model", models if models else ["No models available"])
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.1)

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "image" in message:
            st.image(message["image"])
        st.markdown(message["content"])

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
    db.store_message("user", prompt, selected_model, image_bytes)
    
    message_data = {"role": "user", "content": prompt}
    if uploaded_image:
        message_data["image"] = image_bytes
    st.session_state.messages.append(message_data)

    # Display assistant response with streaming
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        for response_chunk in stream_chat(selected_model, prompt, temperature, image_bytes if uploaded_image else None):
            if response_chunk:
                full_response += response_chunk
                message_placeholder.markdown(full_response + "▌")
        
        if full_response:
            message_placeholder.markdown(full_response)
            # Store assistant's response in database
            db.store_message("assistant", full_response, selected_model)
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        else:
            st.error("No response received from the model. Please check if Ollama is running correctly.")