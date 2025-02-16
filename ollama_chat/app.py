import streamlit as st
import ollama
import json
from typing import Iterator
from PIL import Image
import io

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
            "num_gpu": 0,  # Force CPU usage
            "num_thread": 2  # Reduce number of threads
        }
        
        if image:
            # Convert image to base64 if image is provided
            stream = ollama.generate(
                model=model,
                prompt=message,
                images=[image],
                options=options,
                stream=True
            )
        else:
            stream = ollama.generate(
                model=model,
                prompt=message,
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
    
    message_data = {"role": "user", "content": prompt}
    if uploaded_image:
        image_bytes = uploaded_image.getvalue()
        message_data["image"] = image_bytes
    st.session_state.messages.append(message_data)

    # Display assistant response with streaming
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        
        # Stream the response
        for response_chunk in stream_chat(selected_model, prompt, temperature, image_bytes if uploaded_image else None):
            if response_chunk:  # Only update if we got a valid response
                full_response += response_chunk
                message_placeholder.markdown(full_response + "▌")
        
        # Final response without cursor
        if full_response:
            message_placeholder.markdown(full_response)
            # Add assistant's message to chat history
            st.session_state.messages.append({"role": "assistant", "content": full_response})
        else:
            st.error("No response received from the model. Please check if Ollama is running correctly.")