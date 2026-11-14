The bundled file `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` is OpenAI's
`cl100k_base.tiktoken` vocabulary, used by the MIT-licensed tiktoken package.

SHA-256: `223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`

Canonical source: https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken

Downloaded from Microsoft's identical public copy:
https://huggingface.co/microsoft/phi-4/resolve/c9ce45103d61f048f7915aecc3f42985b63429d5/cl100k_base.tiktoken

The checksum matches the value in tiktoken's `openai_public.py`. Bundling avoids
outbound vocabulary downloads during private-network cold starts. The filename is
the SHA-1 cache key of the canonical URL, as required by tiktoken.
