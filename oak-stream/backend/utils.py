import numpy as np
import onnxruntime
import requests
import cv2
import depthai as dai
from depthai_nodes.node import ParsingNeuralNetwork
from pathlib import Path
from tokenizers import Tokenizer

# ── Configuration & Constants ──────────────────────────────────────────────────
QUANT_ZERO_POINT = 90.0
QUANT_SCALE = 0.003925696481
MAX_NUM_CLASSES = 80
CACHE_DIR = Path("./.yolo_world_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Define your custom classes here (YOLO-World is open-vocabulary!)
MY_CLASSES = [
    "yellow leaf with spots",
    "brown unhealthy leaf",
    "green long leaf",
    "dry patch of grass",
    "green grass"
]

# ── Helper Functions to Download & Compute Embeddings ─────────────────────────

def download_file(url: str, dest: Path) -> str:
    if dest.exists():
        return str(dest)
    print(f"Downloading {dest.name}...")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return str(dest)

def get_clip_onnx_path() -> str:
    """Fetches the official Luxonis CLIP text model URL and downloads it."""
    dest = CACHE_DIR / "clip_textual_hf.onnx"
    if dest.exists():
        return str(dest)
    
    # Query Luxonis Model API for the CLIP companion model
    base_url = "https://easyml.cloud.luxonis.com/models/api/v1"
    model_res = requests.get(f"{base_url}/models", params={"slug": "yolo-world-l", "is_public": True})
    model_res.raise_for_status()
    model_id = model_res.json()[0]["id"]
    
    variant_res = requests.get(
        f"{base_url}/modelVersions",
        params={"model_id": model_id, "variant_slug": "clip-textual-hf", "is_public": True}
    )
    variant_res.raise_for_status()
    variant_id = variant_res.json()[0]["id"]
    
    dl_res = requests.get(f"{base_url}/modelVersions/{variant_id}/download")
    dl_res.raise_for_status()
    download_link = dl_res.json()[0]["download_link"]
    
    return download_file(download_link, dest)

def compute_text_embeddings(class_names: list) -> np.ndarray:
    """Computes compatible [1, 512, 80] uint8 embeddings using the correct CLIP tokenizer."""
    # 1. Download the correct CLIP tokenizer config
    tok_path = download_file(
        "https://huggingface.co/openai/clip-vit-base-patch32/resolve/main/tokenizer.json",
        CACHE_DIR / "tokenizer.json"
    )
    tokenizer = Tokenizer.from_file(tok_path)
    tokenizer.enable_padding(
        pad_id=tokenizer.token_to_id("<|endoftext|>"), 
        pad_token="<|endoftext|>"
    )
    
    # 2. Tokenize class labels
    encodings = tokenizer.encode_batch(class_names)
    text_ids = np.array([e.ids for e in encodings], dtype=np.int64)
    attn_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

    # 3. Get CLIP ONNX path and run inference locally via ONNX Runtime
    onnx_path = get_clip_onnx_path()
    session = onnxruntime.InferenceSession(
        onnx_path, providers=["CPUExecutionProvider"]
    )
    
    input_name = session.get_inputs()[0].name
    text_features = session.run(
        None, {input_name: text_ids, "attention_mask": attn_mask}
    )[0]

    # 4. Pad classes up to MAX_NUM_CLASSES (80)
    num_pad = MAX_NUM_CLASSES - len(class_names)
    text_features = np.pad(text_features, ((0, num_pad), (0, 0)), mode="constant")
    text_features = text_features.T.reshape(1, 512, MAX_NUM_CLASSES)
    
    # 5. Quantize float32 -> uint8 (DepthAI NPU expects quantized features)
    text_features = (
        np.clip(text_features / QUANT_SCALE + QUANT_ZERO_POINT, 0, 255)
        .round()
        .astype(np.uint8)
    )
    return text_features
