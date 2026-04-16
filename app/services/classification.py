from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from torch import nn
from PIL import Image, ImageDraw
from torchvision import transforms
from torchvision.models import mobilenet_v2

from app.core.config import settings
from app.services.image_enhancement import enhance_frame_for_ai


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def _load_labels(labels_path: Path) -> list[str]:
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels file not found at: {labels_path}")

    labels = [line.strip() for line in labels_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not labels:
        raise ValueError(f"Labels file is empty: {labels_path}")
    return labels


def _extract_state_dict(checkpoint: Any) -> dict[str, torch.Tensor]:
    if isinstance(checkpoint, dict):
        for key in ("state_dict", "model_state_dict", "model", "net"):
            value = checkpoint.get(key)
            if isinstance(value, dict):
                checkpoint = value
                break

    if not isinstance(checkpoint, dict):
        raise ValueError("Unsupported checkpoint format for MobileNetV2 weights")

    state_dict: dict[str, torch.Tensor] = {}
    for key, value in checkpoint.items():
        new_key = key[7:] if key.startswith("module.") else key
        if torch.is_tensor(value):
            state_dict[new_key] = value
    if not state_dict:
        raise ValueError("No tensor weights found in MobileNetV2 checkpoint")
    return state_dict


def _square_pad(image: Image.Image) -> Image.Image:
    width, height = image.size
    max_wh = max(width, height)
    pad_left = (max_wh - width) // 2
    pad_top = (max_wh - height) // 2
    pad_right = max_wh - width - pad_left
    pad_bottom = max_wh - height - pad_top
    return transforms.functional.pad(image, (pad_left, pad_top, pad_right, pad_bottom), fill=0)


@lru_cache(maxsize=1)
def load_classification_model(
    model_path: str | None = None,
    labels_path: str | None = None,
    prefer_gpu: bool = True,
) -> tuple[nn.Module, list[str], str]:
    weights_path = Path(model_path or settings.mobilenet_model_path)
    classes_path = Path(labels_path or settings.mobilenet_labels_path)

    if not weights_path.exists():
        raise FileNotFoundError(f"MobileNetV2 weights not found at: {weights_path}")

    labels = _load_labels(classes_path)
    device = "cuda:0" if prefer_gpu and torch.cuda.is_available() else "cpu"

    model = mobilenet_v2(weights=None)
    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, len(labels))

    checkpoint = torch.load(weights_path, map_location="cpu")
    state_dict = _extract_state_dict(checkpoint)

    try:
        model.load_state_dict(state_dict, strict=True)
    except RuntimeError:
        model.load_state_dict(state_dict, strict=False)

    model.to(device)
    model.eval()
    return model, labels, device


def _preprocess_image(image: Image.Image) -> torch.Tensor:
    preprocess = transforms.Compose(
        [
            transforms.Lambda(_square_pad),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ]
    )
    return preprocess(image).unsqueeze(0)


def _predict_attributes_from_pil(image: Image.Image) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    model, labels, device = load_classification_model()
    tensor = _preprocess_image(image).to(device)
    threshold = float(settings.mobilenet_conf_threshold)

    with torch.no_grad():
        logits = model(tensor)
        probs = torch.sigmoid(logits)[0]

    class_results: list[dict[str, Any]] = []
    for idx, class_name in enumerate(labels):
        prob = float(probs[idx].item()) if idx < probs.numel() else 0.0
        class_results.append(
            {
                "class_id": idx,
                "label": class_name,
                "status": "CO" if prob >= threshold else "KHONG",
                "confidence": prob,
            }
        )

    best = max(class_results, key=lambda item: item["confidence"]) if class_results else None
    active_labels = [item for item in class_results if item["confidence"] >= threshold]
    summary_label = " | ".join(f"{item['label']} {item['confidence'] * 100:.1f}%" for item in active_labels)
    if not summary_label and best is not None:
        summary_label = f"{best['label']} {best['confidence'] * 100:.1f}%"

    di_xa = "CO" if active_labels else "KHONG"

    prediction = {
        "classes": class_results,
        "best": best,
        "summary_label": summary_label,
        "DI_XA": di_xa,
    }
    return class_results, prediction, device


def classify_roi(image: np.ndarray) -> tuple[dict[str, Any], str]:
    image = enhance_frame_for_ai(image)
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGB")
    _, prediction, device = _predict_attributes_from_pil(pil_image)
    prediction["device"] = device
    return prediction, device


def classify_image_and_annotate(image: np.ndarray) -> tuple[np.ndarray, dict[str, Any], str]:
    image = enhance_frame_for_ai(image)
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).convert("RGB")
    class_results, prediction, device = _predict_attributes_from_pil(pil_image)

    result_img = Image.new("RGB", (pil_image.width + max(int(pil_image.width * 0.6), 300), pil_image.height), (255, 255, 255))
    result_img.paste(pil_image, (0, 0))
    draw = ImageDraw.Draw(result_img)
    text_x = pil_image.width + 10
    y_offset = 10

    for item in class_results:
        label_text = f"{item['label']}: {item['status']} ({item['confidence'] * 100:.1f}%)"
        draw.text((text_x, y_offset), label_text, fill=(0, 0, 0))
        y_offset += 25

    annotated = cv2.cvtColor(np.array(result_img), cv2.COLOR_RGB2BGR)
    return annotated, prediction, device
