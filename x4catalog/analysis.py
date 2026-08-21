from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable

import numpy as np
from PIL import Image

from .config import CatalogPaths
from .db import connect, event, transaction
from .taxonomy import TAXONOMY


SIGLIP_MODEL = "google/siglip2-so400m-patch14-384"


@dataclass(frozen=True)
class AnalysisResult:
    processed: int
    device: str
    model: str


def _ml_imports():
    try:
        import torch
        from transformers import AutoModel, AutoProcessor
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "ML analysis is optional. Install it once with: uv sync --extra ml"
        ) from exc
    return torch, AutoModel, AutoProcessor


def select_device() -> str:
    torch, _, _ = _ml_imports()
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _prompts() -> list[tuple[str, str]]:
    """Visual-only taxonomy prompts suitable for a general image encoder.

    Review-status and suitability tags are decisions, not visual subjects, so
    they are deliberately excluded from model suggestions. They remain in the
    fixed taxonomy for human review and deterministic X4 checks.
    """
    prompts: list[tuple[str, str]] = []
    for name in TAXONOMY["subject"]:
        prompts.append((name, f"a black and white image that depicts {name.replace('-', ' ')}"))
    for name in TAXONOMY["franchise"]:
        prompts.append((name, f"a black and white image from the {name.replace('-', ' ')} franchise or television series"))
    for name in TAXONOMY["style"]:
        prompts.append((name, f"a black and white image in {name.replace('-', ' ')} style"))
    for name in TAXONOMY["composition"]:
        prompts.append((name, f"a black and white image that is {name.replace('-', ' ')}"))
    return prompts


def _pooled_features(outputs):
    """Support both pre-v5 tensor results and v5 structured feature outputs."""
    return outputs.pooler_output if hasattr(outputs, "pooler_output") else outputs


def _cached_or_one_time_download(loader, model_id: str, cache_dir: str, **kwargs):
    """Use the local model cache first; only a missing cache may reach the hub."""
    try:
        return loader(model_id, cache_dir=cache_dir, local_files_only=True, **kwargs)
    except OSError:
        return loader(model_id, cache_dir=cache_dir, local_files_only=False, **kwargs)


def embed(paths: CatalogPaths, batch_size: int = 12, limit: int | None = None) -> AnalysisResult:
    """Create local float16 embeddings and conservative machine tag suggestions."""
    torch, AutoModel, AutoProcessor = _ml_imports()
    device = select_device()
    # Individual unsupported MPS kernels fall back locally to CPU. This is not
    # a network fallback and keeps the process usable across Apple GPU / CPU
    # PyTorch combinations.
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    os.environ.setdefault("HF_HOME", str(paths.models / "huggingface"))
    paths.models.mkdir(parents=True, exist_ok=True)
    processor = _cached_or_one_time_download(AutoProcessor.from_pretrained, SIGLIP_MODEL, os.environ["HF_HOME"])
    model = _cached_or_one_time_download(
        AutoModel.from_pretrained,
        SIGLIP_MODEL,
        os.environ["HF_HOME"],
        torch_dtype=torch.float16 if device == "mps" else torch.float32,
    ).to(device).eval()
    prompt_pairs = _prompts()
    tag_names = [tag_name for tag_name, _ in prompt_pairs]
    prompts = [prompt for _, prompt in prompt_pairs]
    with torch.inference_mode():
        text_inputs = processor(text=prompts, padding=True, return_tensors="pt").to(device)
        text_vectors = _pooled_features(model.get_text_features(**text_inputs))
        text_vectors = torch.nn.functional.normalize(text_vectors, dim=-1)

    processed = 0
    conn = connect(paths.database)
    try:
        rows = conn.execute(
            "SELECT id, source_path FROM images WHERE id NOT IN (SELECT image_id FROM embeddings) ORDER BY id"
        ).fetchall()
        if limit is not None:
            rows = rows[:limit]
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            images = []
            for row in batch:
                with Image.open(row["source_path"]) as image:
                    images.append(image.convert("RGB").copy())
            with torch.inference_mode():
                inputs = processor(images=images, return_tensors="pt").to(device)
                if device == "mps":
                    inputs["pixel_values"] = inputs["pixel_values"].to(dtype=torch.float16)
                vectors = _pooled_features(model.get_image_features(**inputs))
                vectors = torch.nn.functional.normalize(vectors, dim=-1)
                scores = vectors @ text_vectors.T
            vectors_np = vectors.detach().cpu().numpy().astype(np.float16)
            scores_np = scores.detach().cpu().numpy()
            for row, vector, row_scores in zip(batch, vectors_np, scores_np, strict=True):
                conn.execute(
                    "INSERT OR REPLACE INTO embeddings(image_id, model, dimensions, vector, device) VALUES (?, ?, ?, ?, ?)",
                    (row["id"], SIGLIP_MODEL, int(vector.shape[0]), vector.tobytes(), device),
                )
                # Machine suggestions remain unconfirmed and are intentionally conservative.
                conn.execute("DELETE FROM image_tags WHERE image_id=? AND source='machine'", (row["id"],))
                for index in np.argsort(row_scores)[-4:][::-1]:
                    # SigLIP's raw binary-match logits are conservative for
                    # this niche monochrome corpus. This provisional mapping
                    # is intentionally only a review-ranking confidence; human
                    # confirmation is the authoritative tag signal.
                    confidence = float(1 / (1 + np.exp(-(row_scores[index] + 8.0) / 2.0)))
                    if confidence < 0.5:
                        continue
                    tag_name = tag_names[int(index)]
                    tag = conn.execute("SELECT id FROM tags WHERE name=?", (tag_name,)).fetchone()
                    if tag:
                        conn.execute(
                            "INSERT OR REPLACE INTO image_tags(image_id, tag_id, source, confidence, confirmed) VALUES (?, ?, 'machine', ?, 0)",
                            (row["id"], tag["id"], confidence),
                        )
                processed += 1
            # A batch is the natural inference checkpoint: completed vectors,
            # tags, and their event trail survive a cancellation.
            conn.commit()
        event(conn, "embeddings_created", "run", SIGLIP_MODEL, {"processed": processed, "device": device})
        conn.commit()
    except BaseException:
        conn.commit()
        raise
    finally:
        conn.close()
    return AnalysisResult(processed=processed, device=device, model=SIGLIP_MODEL)


def ocr_source_path() -> Path:
    return Path(__file__).resolve().parent / "vision_ocr.swift"


def compile_ocr_worker(paths: CatalogPaths) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("OCR uses Apple Vision and is available on macOS only.")
    source = ocr_source_path()
    if not source.is_file():
        raise FileNotFoundError(f"OCR helper is missing: {source}")
    paths.runs.mkdir(parents=True, exist_ok=True)
    binary = paths.runs / "vision-ocr"
    if not binary.exists() or source.stat().st_mtime_ns > binary.stat().st_mtime_ns:
        try:
            subprocess.run(["swiftc", str(source), "-o", str(binary)], check=True)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "OCR requires the Swift compiler (swiftc). Install Xcode Command Line Tools."
            ) from exc
    return binary


def ocr(
    paths: CatalogPaths,
    limit: int | None = None,
    checkpoint_every: int = 1,
    workers: int = 4,
) -> int:
    worker = compile_ocr_worker(paths)
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every must be at least 1")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    processed = 0
    processed_since_checkpoint = 0
    conn = connect(paths.database)
    try:
        rows = conn.execute(
            "SELECT id, source_path FROM images WHERE id NOT IN (SELECT image_id FROM ocr_results) ORDER BY id"
        ).fetchall()
        if limit is not None:
            rows = rows[:limit]
        def recognize(row):
            completed = subprocess.run([str(worker), row["source_path"]], capture_output=True, text=True, check=True)
            return row, json.loads(completed.stdout)

        # Vision calls happen concurrently, but the main thread remains the
        # sole SQLite writer. This gives bounded local parallelism without
        # racing catalog mutations.
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="x4-vision") as executor:
            completed_rows = executor.map(recognize, rows)
            for row, payload in completed_rows:
                text = str(payload.get("text", ""))
                density = float(payload.get("text_density", 0.0))
                minimum = payload.get("minimum_text_height")
                small = bool(payload.get("has_small_text", False))
                conn.execute(
                    "INSERT OR REPLACE INTO ocr_results(image_id, text, text_density, minimum_text_height, has_small_text, engine) VALUES (?, ?, ?, ?, ?, 'Apple Vision')",
                    (row["id"], text, density, minimum, int(small)),
                )
                conn.execute("DELETE FROM ocr_fts WHERE image_id=?", (row["id"],))
                conn.execute("INSERT INTO ocr_fts(image_id, text) VALUES (?, ?)", (row["id"], text))
                processed += 1
                processed_since_checkpoint += 1
                if processed_since_checkpoint >= checkpoint_every:
                    conn.commit()
                    processed_since_checkpoint = 0
        event(conn, "ocr_completed", "run", "Apple Vision", {"processed": processed})
        conn.commit()
    except BaseException:
        conn.commit()
        raise
    finally:
        conn.close()
    return processed


def cluster(paths: CatalogPaths, requested_clusters: int = 200) -> int:
    """Small deterministic cosine k-means implementation; no cloud and no extra service."""
    with transaction(paths.database) as conn:
        rows = conn.execute("SELECT image_id, dimensions, vector FROM embeddings ORDER BY image_id").fetchall()
        if not rows:
            raise RuntimeError("No embeddings exist. Run x4catalog embed first.")
        ids = np.asarray([row["image_id"] for row in rows], dtype=np.int64)
        vectors = np.stack([np.frombuffer(row["vector"], dtype=np.float16).astype(np.float32) for row in rows])
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        k = min(requested_clusters, max(1, len(ids) // 8))
        # Deterministic evenly spaced seeds avoid a hidden random-review order.
        centres = vectors[np.linspace(0, len(vectors) - 1, k, dtype=int)].copy()
        for _ in range(30):
            labels = np.argmax(vectors @ centres.T, axis=1)
            updated = np.stack([
                vectors[labels == index].mean(axis=0) if np.any(labels == index) else centres[index]
                for index in range(k)
            ])
            updated /= np.maximum(np.linalg.norm(updated, axis=1, keepdims=True), 1e-12)
            if np.allclose(updated, centres, atol=1e-4):
                break
            centres = updated
        conn.execute("DELETE FROM cluster_members")
        conn.execute("DELETE FROM clusters")
        for index in range(k):
            cluster_id = conn.execute("INSERT INTO clusters(algorithm) VALUES ('cosine-kmeans')").lastrowid
            mask = labels == index
            distances = 1 - (vectors[mask] @ centres[index])
            cutoff = float(np.quantile(distances, 0.9)) if len(distances) > 2 else 1.0
            for image_id, distance in zip(ids[mask], distances, strict=True):
                conn.execute(
                    "INSERT INTO cluster_members(cluster_id, image_id, distance, outlier) VALUES (?, ?, ?, ?)",
                    (cluster_id, int(image_id), float(distance), int(distance >= cutoff)),
                )
        event(conn, "clusters_created", "run", "cosine-kmeans", {"count": k, "images": len(ids)})
    return k


def train_preference(paths: CatalogPaths) -> int:
    with transaction(paths.database) as conn:
        rows = conn.execute(
            """SELECT r.decision, e.vector FROM reviews r JOIN embeddings e ON e.image_id=r.image_id
               WHERE r.decision IN ('keep', 'favorite', 'reject')"""
        ).fetchall()
        if len(rows) < 250:
            raise RuntimeError("Preference training needs at least 250 explicit keep/reject/favorite decisions.")
        labels = np.asarray([0.0 if row["decision"] == "reject" else 1.0 for row in rows], dtype=np.float32)
        vectors = np.stack([np.frombuffer(row["vector"], dtype=np.float16).astype(np.float32) for row in rows])
        weights = np.zeros(vectors.shape[1], dtype=np.float32)
        bias = 0.0
        for _ in range(400):
            scores = vectors @ weights + bias
            probabilities = 1 / (1 + np.exp(-np.clip(scores, -30, 30)))
            error = probabilities - labels
            weights -= 0.04 * ((vectors.T @ error) / len(labels) + 0.001 * weights)
            bias -= 0.04 * float(error.mean())
        model_id = conn.execute(
            "INSERT INTO preference_models(version, dimensions, weights, bias, sample_count) VALUES ('logistic-v1', ?, ?, ?, ?)",
            (len(weights), weights.astype(np.float32).tobytes(), bias, len(labels)),
        ).lastrowid
        all_rows = conn.execute("SELECT image_id, vector FROM embeddings").fetchall()
        for row in all_rows:
            vector = np.frombuffer(row["vector"], dtype=np.float16).astype(np.float32)
            score = float(1 / (1 + np.exp(-np.clip(vector @ weights + bias, -30, 30))))
            conn.execute("INSERT OR REPLACE INTO preference_scores(image_id, model_id, score) VALUES (?, ?, ?)", (row["image_id"], model_id, score))
        event(conn, "preference_model_trained", "model", model_id, {"sample_count": len(labels)})
    return model_id
