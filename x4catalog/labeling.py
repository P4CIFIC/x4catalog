"""Local ensemble labeling for the X4 catalog.

The catalog keeps the original BMPs immutable.  This module only reads source
images and writes derived SQLite predictions, model caches, and generated
views.  Model imports are deliberately lazy so the base catalog remains usable
without downloading ML packages.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import gc
import json
import os
from pathlib import Path
import re
from typing import Iterable, Sequence

import numpy as np
from PIL import Image

from .analysis import SIGLIP_MODEL, _pooled_features, select_device
from .catalog import initialize_catalog, rebuild_views
from .config import CatalogPaths
from .db import connect, event, get_setting, set_setting, transaction
from .taxonomy import TAXONOMY


MODEL_BUNDLE = "rampp-wd14-marqo-siglip-v2"
RAM_REPO = "xinyu1205/recognize-anything-plus-model"
RAM_CHECKPOINT = "ram_plus_swin_large_14m.pth"
WD14_REPO = "SmilingWolf/wd-eva02-large-tagger-v3"
NSFW_REPO = "Marqo/nsfw-image-detection-384"
BERT_REPO = "bert-base-uncased"

MODEL_REVISIONS = {
    "rampp": "ram_plus_swin_large_14m.pth@main",
    "wd14": "wd-eva02-large-tagger-v3@main-top128-v2",
    "nsfw": "nsfw-image-detection-384@main",
    "bert": "bert-base-uncased@main",
    "siglip": f"{SIGLIP_MODEL}@franchise-v2",
}

DEFAULT_MODELS = ("rampp", "wd14", "nsfw", "siglip")
LABEL_MODEL_REVISIONS = {model: MODEL_REVISIONS[model] for model in DEFAULT_MODELS}
MIN_PUBLISH_CONFIDENCE = 0.80
CONFIDENCE_POLICY_REVISION = "uniform-publish-0.80-v2"

ALIASES = {
    "black-and-white": "binary-black-white",
    "black_white": "binary-black-white",
    "monochrome": "grayscale",
    "solo": "single-subject",
    "simple-background": "large-empty-space",
    "simple_background": "large-empty-space",
    "white-background": "mostly-white",
    "black-background": "mostly-black",
    "high_contrast": "high-contrast",
    "dramatic-lighting": "dramatic",
    "dramatic_lighting": "dramatic",
    "thick-lines": "heavy-ink",
    "thick_lines": "heavy-ink",
    "nude": "nudity",
    "naked": "nudity",
    "topless": "partial-nudity",
    "nipples": "nudity",
    "lingerie": "suggestive",
    "underwear": "suggestive",
    "bondage": "fetish",
    "sexual": "sexualized",
    "sex": "sexualized",
    "blood": "gore",
    "violent": "violence",
    "rating-explicit": "nsfw",
    "rating-questionable": "suggestive",
    "rating_safe": None,
    "rating-s": None,
}

SKIP_PREFIXES = ("artist:", "copyright:", "meta:", "year:")
SKIP_LABELS = {"safe", "general", "questionable", "sensitive", "nsfw-safe"}


@dataclass(frozen=True)
class Prediction:
    raw_label: str
    score: float
    model: str


def _confidence_band(score: float) -> str:
    if score >= MIN_PUBLISH_CONFIDENCE:
        return "likely"
    if score >= 0.55:
        return "possible"
    return "weak"


def _is_publishable(model: str, score: float, tag_id: int | None) -> bool:
    """Keep uncertain predictions as evidence, never as automatic catalog tags."""
    return tag_id is not None and score >= MIN_PUBLISH_CONFIDENCE


def _slug(value: str) -> str:
    value = value.casefold().strip().replace("_", "-").replace(" ", "-")
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    return re.sub(r"-{2,}", "-", value).strip("-")


def normalize_label(raw_label: str) -> str | None:
    """Map model vocabulary to X4 names, retaining unknown visual tags safely."""
    raw = raw_label.strip().casefold()
    if not raw:
        return None
    if any(raw.startswith(prefix) for prefix in SKIP_PREFIXES):
        return None
    if raw.startswith("character:"):
        raw = raw.split(":", 1)[1]
    if raw.startswith("rating:"):
        raw = raw.replace(":", "-")
    slug = _slug(raw)
    if slug in SKIP_LABELS:
        return None
    if slug in ALIASES:
        return ALIASES[slug]
    return slug if 2 <= len(slug) <= 64 else None


def _category_for(name: str) -> str:
    for category, values in TAXONOMY.items():
        if name in values:
            return category
    return "model"


def _ensure_tag(conn, name: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO tags(name, category) VALUES (?, ?)",
        (name, _category_for(name)),
    )
    return int(conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[0])


def _cached_model_env(paths: CatalogPaths) -> None:
    paths.models.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(paths.models / "huggingface"))
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def download_models(paths: CatalogPaths) -> dict[str, object]:
    """Download the approved model bundle once; inference never calls the hub."""
    paths.ensure()
    hf_home = paths.models / "huggingface"
    hf_home.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install ML dependencies first with: uv sync --extra ml") from exc

    os.environ["HF_HOME"] = str(hf_home)
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    snapshots = {
        "wd14": snapshot_download(WD14_REPO, cache_dir=str(hf_home)),
        "nsfw": snapshot_download(NSFW_REPO, cache_dir=str(hf_home)),
        "bert": snapshot_download(
            BERT_REPO,
            cache_dir=str(hf_home),
            allow_patterns=[
                "config.json",
                "special_tokens_map.json",
                "tokenizer_config.json",
                "tokenizer.json",
                "vocab.txt",
            ],
        ),
    }
    ram_path = hf_hub_download(
        RAM_REPO,
        RAM_CHECKPOINT,
        cache_dir=str(hf_home),
    )
    manifest = {
        "bundle": MODEL_BUNDLE,
        "models": {
            "rampp": {"repo": RAM_REPO, "file": ram_path},
            "wd14": {"repo": WD14_REPO, "snapshot": snapshots["wd14"]},
            "nsfw": {"repo": NSFW_REPO, "snapshot": snapshots["nsfw"]},
            "bert": {"repo": BERT_REPO, "snapshot": snapshots["bert"]},
            "siglip": {"repo": SIGLIP_MODEL, "cache": str(hf_home)},
        },
    }
    manifest_path = paths.models / "model-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return {"manifest": str(manifest_path), "bundle": MODEL_BUNDLE}


def _require_checkpoint(paths: CatalogPaths) -> Path:
    manifest_path = paths.models / "model-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
            recorded = Path(manifest["models"]["rampp"]["file"])
            if recorded.is_file():
                return recorded
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            pass
    candidates = [
        paths.models / RAM_CHECKPOINT,
        paths.models / "ram" / RAM_CHECKPOINT,
        paths.models / "huggingface" / "models--xinyu1205--recognize-anything-plus-model" / "snapshots",
        paths.models / "huggingface" / "hub" / "models--xinyu1205--recognize-anything-plus-model" / "snapshots",
    ]
    for candidate in candidates[:2]:
        if candidate.is_file():
            return candidate
    for snapshots in candidates[2:]:
        if snapshots.is_dir():
            matches = sorted(snapshots.glob(f"*/{RAM_CHECKPOINT}"))
            if matches:
                return matches[-1]
    raise RuntimeError(
        "RAM++ weights are missing. Run: uv run --extra ml x4catalog download-models"
    )


def _require_tokenizer(paths: CatalogPaths) -> Path:
    manifest_path = paths.models / "model-manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
            recorded = Path(manifest["models"]["bert"]["snapshot"])
            if recorded.is_dir() and (recorded / "vocab.txt").is_file():
                return recorded
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            pass
    raise RuntimeError(
        "RAM++ tokenizer is missing. Run: uv run --extra ml x4catalog download-models"
    )


def _require_snapshot(paths: CatalogPaths, model_name: str) -> Path:
    manifest_path = paths.models / "model-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text())
        snapshot = Path(manifest["models"][model_name]["snapshot"])
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"{model_name} model snapshot is missing. Run: uv run --extra ml x4catalog download-models"
        ) from exc
    if not snapshot.is_dir():
        raise RuntimeError(
            f"{model_name} model snapshot is missing. Run: uv run --extra ml x4catalog download-models"
        )
    return snapshot


def _load_local_timm_model(timm, torch, snapshot: Path):
    config_path = snapshot / "config.json"
    weights_path = snapshot / "model.safetensors"
    if not config_path.is_file() or not weights_path.is_file():
        raise RuntimeError(f"Incomplete local model snapshot: {snapshot}")
    config = json.loads(config_path.read_text())
    model = timm.create_model(
        config["architecture"],
        pretrained=False,
        num_classes=int(config.get("num_classes", 1000)),
        pretrained_cfg=config.get("pretrained_cfg"),
        **config.get("model_args", {}),
    )
    from safetensors.torch import load_file

    state_dict = load_file(str(weights_path), device="cpu")
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if missing or unexpected:
        raise RuntimeError(
            f"Local model weights do not match {config['architecture']}: "
            f"missing={list(missing)[:5]}, unexpected={list(unexpected)[:5]}"
        )
    return model, config


class TimmTagger:
    def __init__(self, paths: CatalogPaths, repo_id: str, model_name: str, threshold: float = 0.25):
        _cached_model_env(paths)
        try:
            import timm
            import torch
        except ModuleNotFoundError as exc:
            raise RuntimeError("Install ML dependencies first with: uv sync --extra ml") from exc
        self.torch = torch
        self.model_name = model_name
        self.threshold = threshold
        self.device = select_device()
        snapshot = _require_snapshot(paths, model_name)
        self.model, config = _load_local_timm_model(timm, torch, snapshot)
        self.model = self.model.eval().to(self.device)
        data_config = timm.data.resolve_model_data_config(self.model)
        self.transform = timm.data.create_transform(**data_config, is_training=False)
        cfg = config.get("pretrained_cfg", {})
        names = config.get("label_names") or cfg.get("label_names") or cfg.get("labels") or cfg.get("class_names")
        if not names and (tag_file := snapshot / "selected_tags.csv").is_file():
            with tag_file.open(newline="", encoding="utf-8") as stream:
                names = [row["name"] for row in csv.DictReader(stream)]
        if isinstance(names, dict):
            names = [names[key] for key in sorted(names, key=lambda value: int(value))]
        if not names:
            raise RuntimeError(f"{repo_id} did not expose label names in its timm config")
        self.labels = list(names)

    def predict(self, images: Sequence[Image.Image]) -> list[list[Prediction]]:
        tensors = self.torch.stack([self.transform(image) for image in images]).to(self.device)
        with self.torch.inference_mode():
            outputs = self.model(tensors)
            logits = outputs.logits if hasattr(outputs, "logits") else outputs
            probabilities = logits.sigmoid().detach().cpu().numpy()
        result: list[list[Prediction]] = []
        top_k = 128 if self.model_name == "wd14" else 32
        for row in probabilities:
            indices = np.argsort(row)[-top_k:][::-1]
            result.append([
                Prediction(self.labels[int(index)], float(row[index]), self.model_name)
                for index in indices
                if float(row[index]) >= self.threshold
            ])
        return result


class NsfwTagger(TimmTagger):
    def __init__(self, paths: CatalogPaths):
        super().__init__(paths, NSFW_REPO, "nsfw", threshold=0.0)

    def predict(self, images: Sequence[Image.Image]) -> list[list[Prediction]]:
        tensors = self.torch.stack([self.transform(image) for image in images]).to(self.device)
        with self.torch.inference_mode():
            outputs = self.model(tensors)
            logits = outputs.logits if hasattr(outputs, "logits") else outputs
            probabilities = logits.softmax(dim=-1).detach().cpu().numpy()
        nsfw_index = next(
            (index for index, name in enumerate(self.labels) if "nsfw" in str(name).casefold()),
            min(1, probabilities.shape[1] - 1),
        )
        result: list[list[Prediction]] = []
        for row in probabilities:
            score = float(row[nsfw_index])
            result.append([Prediction("nsfw", score, "nsfw")] if score >= 0.35 else [])
        return result


class RamPlusTagger:
    def __init__(self, paths: CatalogPaths):
        _cached_model_env(paths)
        try:
            import torch
            from ram import get_transform, inference_ram
            from ram.models import ram_plus
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Install RAM++ with the ML extra, then run download-models: uv sync --extra ml"
            ) from exc
        self.torch = torch
        self.inference = inference_ram
        self.transform = get_transform(image_size=384)
        self.device = select_device()
        self.model = ram_plus(
            pretrained=str(_require_checkpoint(paths)),
            image_size=384,
            vit="swin_l",
            text_encoder_type=str(_require_tokenizer(paths)),
        ).eval().to(self.device)

    def predict(self, images: Sequence[Image.Image]) -> list[list[Prediction]]:
        result: list[list[Prediction]] = []
        for image in images:
            tensor = self.transform(image).unsqueeze(0).to(self.device)
            with self.torch.inference_mode():
                output = self.inference(tensor, self.model)
            labels = output[0] if isinstance(output, (tuple, list)) else output
            if isinstance(labels, (tuple, list)):
                labels = labels[0] if labels else ""
            raw_labels = [value.strip() for value in str(labels).split(" | ") if value.strip()]
            result.append([Prediction(value, 0.75, "rampp") for value in raw_labels])
        return result


class SiglipTaxonomyScorer:
    def __init__(self, paths: CatalogPaths):
        _cached_model_env(paths)
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ModuleNotFoundError as exc:
            raise RuntimeError("Install ML dependencies first with: uv sync --extra ml") from exc
        self.torch = torch
        self.device = select_device()
        cache_dir = os.environ["HF_HOME"]
        self.processor = AutoProcessor.from_pretrained(SIGLIP_MODEL, cache_dir=cache_dir, local_files_only=True)
        self.model = AutoModel.from_pretrained(
            SIGLIP_MODEL,
            cache_dir=cache_dir,
            local_files_only=True,
            torch_dtype=torch.float16 if self.device == "mps" else torch.float32,
        ).eval().to(self.device)
        self.prompt_pairs = self._prompts()
        prompts = [prompt for _, prompt in self.prompt_pairs]
        with torch.inference_mode():
            inputs = self.processor(text=prompts, padding=True, return_tensors="pt").to(self.device)
            vectors = _pooled_features(self.model.get_text_features(**inputs))
            self.text_vectors = torch.nn.functional.normalize(vectors, dim=-1).detach().cpu().numpy()

    @staticmethod
    def _prompts() -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for category in ("subject", "franchise", "style", "composition", "display", "content", "intensity"):
            for name in TAXONOMY[category]:
                if category == "content":
                    prompt = f"a black and white image with {name.replace('-', ' ')} content"
                elif category == "intensity":
                    prompt = f"a bold visual design that is {name.replace('-', ' ')}"
                elif category == "franchise":
                    prompt = f"a black and white image from the {name.replace('-', ' ')} franchise or television series"
                else:
                    prompt = f"a black and white e-paper image that depicts {name.replace('-', ' ')}"
                pairs.append((name, prompt))
        return pairs

    def predict(self, rows: Sequence[tuple[int, bytes]]) -> dict[int, list[Prediction]]:
        if not rows:
            return {}
        vectors = np.stack([
            np.frombuffer(vector, dtype=np.float16).astype(np.float32) for _, vector in rows
        ])
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        scores = vectors @ self.text_vectors.T
        grouped: dict[str, list[tuple[int, str]]] = {}
        for index, (name, _) in enumerate(self.prompt_pairs):
            category = _category_for(name)
            grouped.setdefault(category, []).append((index, name))
        result: dict[int, list[Prediction]] = {image_id: [] for image_id, _ in rows}
        for row_index, (image_id, _) in enumerate(rows):
            for category, values in grouped.items():
                category_scores = sorted(
                    ((scores[row_index, index], name) for index, name in values),
                    reverse=True,
                )[:3]
                for score, name in category_scores:
                    confidence = float(1 / (1 + np.exp(-(float(score) - 0.15) * 16)))
                    if confidence >= 0.52:
                        result[image_id].append(Prediction(name, confidence, "siglip"))
        return result


def _persist_predictions(
    conn,
    run_id: int,
    image_id: int,
    predictions: Iterable[Prediction],
) -> None:
    for prediction in predictions:
        normalized = normalize_label(prediction.raw_label)
        tag_id = _ensure_tag(conn, normalized) if normalized else None
        score = min(1.0, max(0.0, float(prediction.score)))
        conn.execute(
            """INSERT INTO label_predictions(
                image_id, model, model_revision, raw_label, tag_id, score,
                confidence_band, published, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_id, model, model_revision, raw_label) DO UPDATE SET
                tag_id=excluded.tag_id, score=excluded.score,
                confidence_band=excluded.confidence_band, published=excluded.published,
                run_id=excluded.run_id, created_at=CURRENT_TIMESTAMP""",
            (
                image_id,
                prediction.model,
                MODEL_REVISIONS[prediction.model],
                prediction.raw_label,
                tag_id,
                score,
                _confidence_band(score),
                int(_is_publishable(prediction.model, score, tag_id)),
                run_id,
            ),
        )


def _pending_rows(conn, model: str, limit: int | None) -> list[object]:
    rows = conn.execute(
        """SELECT id, source_path FROM images
           WHERE state='indexed' AND id NOT IN (
             SELECT image_id FROM label_predictions WHERE model=? AND model_revision=?
           ) ORDER BY id""",
        (model, MODEL_REVISIONS[model]),
    ).fetchall()
    return rows[:limit] if limit is not None else rows


def _run_image_labeler(paths: CatalogPaths, conn, run_id: int, model: str, rows: Sequence[object], batch_size: int) -> int:
    if model == "rampp":
        labeler = RamPlusTagger(paths)
    elif model == "wd14":
        labeler = TimmTagger(paths, WD14_REPO, "wd14", threshold=0.25)
    elif model == "nsfw":
        labeler = NsfwTagger(paths)
    else:
        raise ValueError(f"Unsupported image labeler: {model}")
    processed = 0
    try:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            images = []
            for row in batch:
                with Image.open(row["source_path"]) as image:
                    images.append(image.convert("RGB").copy())
            outputs = labeler.predict(images)
            for row, predictions in zip(batch, outputs, strict=True):
                _persist_predictions(conn, run_id, int(row["id"]), predictions)
            processed += len(batch)
            conn.execute("UPDATE label_runs SET processed=? WHERE id=?", (processed, run_id))
            conn.commit()
    finally:
        del labeler
        gc.collect()
    return processed


def _run_siglip_labeler(paths: CatalogPaths, conn, run_id: int, rows: Sequence[object], batch_size: int) -> int:
    labeler = SiglipTaxonomyScorer(paths)
    processed = 0
    try:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            embeddings = [(int(row["image_id"]), row["vector"]) for row in conn.execute(
                f"SELECT image_id, vector FROM embeddings WHERE image_id IN ({','.join('?' for _ in batch)})",
                [int(row["id"]) for row in batch],
            ).fetchall()]
            outputs = labeler.predict(embeddings)
            for image_id, predictions in outputs.items():
                _persist_predictions(conn, run_id, image_id, predictions)
            processed += len(batch)
            conn.execute("UPDATE label_runs SET processed=? WHERE id=?", (processed, run_id))
            conn.commit()
    finally:
        del labeler
        gc.collect()
    return processed


def _publish_machine_tags(conn, image_ids: Sequence[int], models: Sequence[str]) -> int:
    if not image_ids:
        return 0
    placeholders = ",".join("?" for _ in image_ids)
    conn.execute(
        f"DELETE FROM image_tags WHERE source='machine' AND image_id IN ({placeholders})",
        list(image_ids),
    )
    revision_clauses: list[str] = []
    revision_params: list[object] = []
    for model in DEFAULT_MODELS:
        if model in models:
            revision_clauses.append("(p.model=? AND p.model_revision=?)")
            revision_params.extend((model, LABEL_MODEL_REVISIONS[model]))
        else:
            revision_clauses.append("p.model=?")
            revision_params.append(model)
    revision_clause_sql = " OR ".join(revision_clauses)
    rows = conn.execute(
        f"""SELECT p.image_id, p.tag_id, MAX(p.score) AS score
            FROM label_predictions p
            WHERE p.published=1 AND p.tag_id IS NOT NULL
              AND p.image_id IN ({placeholders}) AND ({revision_clause_sql})
            GROUP BY p.image_id, p.tag_id""",
        [*image_ids, *revision_params],
    ).fetchall()
    for row in rows:
        conn.execute(
            """INSERT INTO image_tags(image_id, tag_id, source, confidence, confirmed)
               VALUES (?, ?, 'machine', ?, 0)
               ON CONFLICT(image_id, tag_id, source) DO UPDATE SET confidence=excluded.confidence""",
            (row["image_id"], row["tag_id"], row["score"]),
        )
    return len(rows)


def reclassify_predictions(paths: CatalogPaths) -> dict[str, object]:
    """Apply the current confidence policy without rerunning image inference."""
    initialize_catalog(paths)
    with transaction(paths.database) as conn:
        if get_setting(conn, "confidence_policy_revision") == CONFIDENCE_POLICY_REVISION:
            return {"policy": CONFIDENCE_POLICY_REVISION, "changed": False}

        conn.execute("UPDATE label_predictions SET published=0")
        conn.execute(
            """UPDATE label_predictions SET confidence_band = CASE
                   WHEN score >= ? THEN 'likely'
                   WHEN score >= ? THEN 'possible'
                   ELSE 'weak' END""",
            (MIN_PUBLISH_CONFIDENCE, 0.55),
        )
        revision_clauses = []
        revision_params: list[object] = []
        for model in DEFAULT_MODELS:
            revision_clauses.append("(model=? AND model_revision=?)")
            revision_params.extend((model, LABEL_MODEL_REVISIONS[model]))
        published_query = (
            "UPDATE label_predictions SET published=1 "
            "WHERE tag_id IS NOT NULL AND score >= ? AND ("
            + " OR ".join(revision_clauses)
            + ")"
        )
        conn.execute(published_query, [MIN_PUBLISH_CONFIDENCE, *revision_params])
        image_ids = [int(row[0]) for row in conn.execute("SELECT id FROM images WHERE state='indexed'").fetchall()]
        published_tags = _publish_machine_tags(conn, image_ids, DEFAULT_MODELS)
        published_predictions = int(conn.execute("SELECT COUNT(*) FROM label_predictions WHERE published=1").fetchone()[0])
        set_setting(conn, "confidence_policy_revision", CONFIDENCE_POLICY_REVISION)
        event(conn, "confidence_policy_applied", "policy", CONFIDENCE_POLICY_REVISION, {
            "minimum_publish_confidence": MIN_PUBLISH_CONFIDENCE,
            "published_predictions": published_predictions,
            "published_tags": published_tags,
        })
    return {
        "policy": CONFIDENCE_POLICY_REVISION,
        "changed": True,
        "minimum_publish_confidence": MIN_PUBLISH_CONFIDENCE,
        "published_predictions": published_predictions,
        "published_tags": published_tags,
    }


def auto_label(
    paths: CatalogPaths,
    *,
    models: Sequence[str] = DEFAULT_MODELS,
    batch_size: int = 8,
    limit: int | None = None,
) -> dict[str, object]:
    """Run the local ensemble with per-batch SQLite checkpoints and resume."""
    invalid = set(models) - set(DEFAULT_MODELS)
    if invalid:
        raise ValueError(f"Unknown labeler(s): {', '.join(sorted(invalid))}")
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    initialize_catalog(paths)
    reclassify_predictions(paths)
    _cached_model_env(paths)
    with transaction(paths.database) as conn:
        rows = conn.execute("SELECT id, source_path FROM images WHERE state='indexed' ORDER BY id").fetchall()
        if limit is not None:
            rows = rows[:limit]
        device = select_device()
        for model in models:
            revision = LABEL_MODEL_REVISIONS[model]
            conn.execute(
                "UPDATE label_predictions SET published=0 WHERE model=? AND model_revision<>?",
                (model, revision),
            )
        run_id = conn.execute(
            "INSERT INTO label_runs(bundle, status, device, total) VALUES (?, 'running', ?, ?)",
            (MODEL_BUNDLE, device, len(rows) * len(models)),
        ).lastrowid
    processed_by_model: dict[str, int] = {}
    try:
        conn = connect(paths.database)
        try:
            for model in models:
                pending = _pending_rows(conn, model, limit)
                if not pending:
                    processed_by_model[model] = 0
                    continue
                if model == "siglip":
                    processed_by_model[model] = _run_siglip_labeler(paths, conn, int(run_id), pending, batch_size)
                else:
                    processed_by_model[model] = _run_image_labeler(paths, conn, int(run_id), model, pending, batch_size)
            image_ids = [int(row["id"]) for row in rows]
            published = _publish_machine_tags(conn, image_ids, models)
            event(conn, "automatic_labels_published", "run", run_id, {
                "bundle": MODEL_BUNDLE,
                "models": list(models),
                "processed_by_model": processed_by_model,
                "published_tags": published,
            })
            conn.execute(
                "UPDATE label_runs SET status='completed', finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()
    except BaseException as exc:
        with transaction(paths.database) as conn:
            conn.execute(
                "UPDATE label_runs SET status='failed', finished_at=CURRENT_TIMESTAMP, error=? WHERE id=?",
                (str(exc), run_id),
            )
        raise
    return {
        "run_id": int(run_id),
        "bundle": MODEL_BUNDLE,
        "device": device,
        "processed_by_model": processed_by_model,
        "published_tags": published,
    }
