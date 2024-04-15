import os
import shutil
import json
import argparse
import socket
import gradio as gr
from rag_chatbot import RAGPipeline, run_ollama_server

parser = argparse.ArgumentParser()
parser.add_argument(
    "--host", type=str, default="host.docker.internal",
    help="Set host to local or in docker container"
)
parser.add_argument(
    "--share", action='store_true',
    help="Share gradio app"
)
args = parser.parse_args()


INPUT_DIR = os.path.join(os.getcwd(), "data/data")
if not os.path.exists(INPUT_DIR):
    os.makedirs(INPUT_DIR)
rag_pipeline = RAGPipeline(host=args.host)

if args.host != "host.docker.internal":
    def is_port_open(port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect(('localhost', port))
                return True
            except ConnectionRefusedError:
                return False
    port_number = 11434
    if not is_port_open(port_number):
        run_ollama_server()

with gr.Blocks(theme=gr.themes.Soft(primary_hue="emerald")) as demo:
    gr.Markdown("# Chat with Multiple PDFs")
    with gr.Tab("Chatbot Interface"):
        with gr.Row(variant='panel', equal_height=True):
            with gr.Column(variant='panel', scale=10):
                documents = gr.Files(
                    label="Add Documents",
                    value=[],
                    file_types=[".txt", ".pdf", ".csv"],
                    file_count="multiple",
                    height=150
                )
                doc_progress = gr.Textbox(
                    label="Status",
                    value="Ready",
                    interactive=False,
                )
                with gr.Column():
                    chat_mode = gr.Radio(
                        label="Mode",
                        choices=["chat", "retrieve", "summary"],
                        value="retrieve",
                        interactive=True
                    )
                    language = gr.Radio(
                        label="Language",
                        choices=["vi", "eng"],
                        value="eng",
                        interactive=True
                    )
                model = gr.Dropdown(
                    label="Set Model",
                    choices=[
                        "mistral:7b-instruct-v0.2-q6_K",
                        "starling-lm:7b-beta-q6_K",
                        "gpt-3.5-turbo"
                    ],
                    value="starling-lm:7b-beta-q6_K",
                    interactive=True,
                    allow_custom_value=True
                )
                pull_btn = gr.Button("Set Model")

            with gr.Column(scale=30, variant="panel"):
                chatbot = gr.Chatbot(layout='bubble', value=[], scale=2)
                with gr.Row(variant='panel'):
                    message = gr.Textbox(label="Enter Prompt:", scale=5, lines=1)
                with gr.Row(variant='panel'):
                    reset_btn = gr.Button(value="Reset")
                    clear_btn = gr.Button(value="Clear")
                    undo_btn = gr.Button(value="Undo")

    with gr.Tab("Retrieval Process"):
        gr.Markdown("ok")

    # @send_btn.click(inputs=[message, chatbot, chat_mode], outputs=[message, chatbot])
    @message.submit(inputs=[message, chatbot, chat_mode], outputs=[message, chatbot])
    def get_respone(message, chatbot, mode, progress=gr.Progress(track_tqdm=True)):
        user_mess = message
        all_text = []
        for text in rag_pipeline.query(user_mess, mode):
            all_text.append(text)
            yield "", chatbot + [[user_mess, "".join(all_text)]]

    @clear_btn.click(outputs=[message, chatbot])
    @model.change(outputs=[message, chatbot])
    @chat_mode.change(outputs=[message, chatbot])
    def clear_chat():
        return "", []

    @undo_btn.click(inputs=[message, chatbot], outputs=[message, chatbot])
    def undo_chat(message, history):
        if len(history) > 0:
            history.pop(-1)
            return "", history
        return "", []

    @reset_btn.click(outputs=[message, chatbot, documents])
    def reset_chat():
        rag_pipeline.reset_index()
        rag_pipeline.reset_query_engine()
        return "", [], None

    @pull_btn.click(inputs=[model], outputs=[message, chatbot])
    def set_model(model, progress=gr.Progress(track_tqdm=True)):
        if model in ["gpt-3.5-turbo", "gpt-4"]:
            rag_pipeline.set_model(model)
        elif not rag_pipeline.check_exist(model):
            response = rag_pipeline.pull_model(model)
            if response.status_code == 200:
                gr.Info(f"Pulling {model}!")
                for data in response.iter_lines(chunk_size=1):
                    data = json.loads(data)
                    if 'completed' in data.keys() and 'total' in data.keys():
                        progress(data['completed'] / data['total'], desc="Downloading")
                    else:
                        progress(0.)
            else:
                gr.Warning(f"Model {model} doesn't exist!")
            rag_pipeline.set_model(model)
        else:
            rag_pipeline.set_model(model)
        gr.Info(f"Model {model} is ready!")
        return "", []

    @documents.change(inputs=[model, documents], outputs=[message, chatbot])
    def set_model_with_docs(model, document):
        if document is not None:
            return set_model(model)
        return "", []

    @chat_mode.change(inputs=[documents, language, chat_mode], outputs=[doc_progress])
    @documents.change(inputs=[documents, language, chat_mode], outputs=[doc_progress])
    def processing_document(
        document, language, mode,
        progress=gr.Progress(track_tqdm=True)
    ):
        if document is not None:
            gr.Info("Processing Document!")
            if args.host == "host.docker.internal":
                for file_path in document:
                    shutil.move(src=file_path, dst=os.path.join(INPUT_DIR, file_path.split("/")[-1]))
                documents = rag_pipeline.get_documents(input_dir=INPUT_DIR)
            else:
                documents = rag_pipeline.get_documents(input_files=document)
            gr.Info("Indexing!")
            rag_pipeline.set_engine(documents, language, mode)
            gr.Info("Processing Completed!")
            return "Completed!"
        else:
            return "Empty Documents"

    @language.change(inputs=[language])
    def change_language(language):
        gr.Info(f"Change language to {language}")

demo.launch(share=args.share, server_name="0.0.0.0")
