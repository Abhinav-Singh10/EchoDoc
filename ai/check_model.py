import time

from huggingface_hub import hf_hub_download
from llama_cpp import Llama

print("Finding or downloading the model...", flush=True)

model_path = hf_hub_download(
    repo_id="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
)

print(f"Model file: {model_path}")
print("Loading model...", flush=True)

started = time.perf_counter()

model = Llama(
    model_path=model_path,
    n_ctx=2048, # context capacity
    n_threads=4, # use 4 cpus for generation
    n_gpu_layers=0, # keep model layers on the CPU
    chat_format="chatml", # chatml is a layout used by this model
    verbose=False, # no runtime diagnostics
)

print(f"Model loaded in {time.perf_counter() - started:.2f} seconds")

tasks = [
    (
        "Grammar correction",
        "Correct the grammar. Preserve the meaning and technical terms. "
        "Return only the corrected text.",
        "The server send events every second. Each clients receives "
        "the updates until it disconnect.",
    ),
    (
        "Summary",
        "Summarize the notes in two short bullet points. "
        "Use only information from the notes.",
        "The browser sends gRPC-Web requests to Envoy. Envoy translates "
        "them into native gRPC requests for the Python server. "
        "GetServerInfo returns one response. WatchEvents keeps sending "
        "events until the client cancels its subscription.",
    ),
]

for name, instruction, text in tasks:
    print(f"\n{name}", flush=True)
    print(f"Input: {text}", flush=True)

    started = time.perf_counter()

    # run local inference
    response = model.create_chat_completion(
        messages=[
            {"role": "system", "content": instruction},
            {"role": "user", "content": text},
        ],
        temperature=0,
        max_tokens=128,
    )

    elapsed = time.perf_counter() - started
    choice = response["choices"][0]

    print(f"Output: {choice['message']['content']}")
    print(f"Time: {elapsed:.2f} seconds")
    print(f"Output tokens: {response['usage']['completion_tokens']}")
    print(f"Finish reason: {choice['finish_reason']}")

model.close()