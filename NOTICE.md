# Third-party notices

X4 Catalog itself is dedicated to the public domain under the Unlicense.
Optional model downloads and Python packages keep their own licenses.

## Optional model packages

These are downloaded only if you run `uv sync --extra ml` and
`x4catalog download-models`. They are not required to browse, tag by hand,
or send images to an X4.

| Component | Source | Notes |
| --- | --- | --- |
| RAM++ | [xinyu1205/recognize-anything](https://github.com/xinyu1205/recognize-anything) and `xinyu1205/recognize-anything-plus-model` | Broad image tags |
| WD14 tagger | `SmilingWolf/wd-eva02-large-tagger-v3` | Visual tags |
| NSFW classifier | `Marqo/nsfw-image-detection-384` | Content tags |
| BERT tokenizer | `bert-base-uncased` | Tokenizer files used with RAM++ |
| SigLIP2 | `google/siglip2-so400m-patch14-384` | Embeddings and taxonomy prompts |

Check each Hugging Face repository and GitHub project for the license that
applies to weights and code before you redistribute a bundle that includes
them.

## OCR

On-device OCR uses Apple's Vision framework through a small Swift helper.
That path is macOS-only and is not used unless you run `x4catalog ocr`.

## XTEINK / CrossPoint

XTEINK, X4, and CrossPoint are names of third-party hardware and firmware.
This project is not affiliated with those vendors.
