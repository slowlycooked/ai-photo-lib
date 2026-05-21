from __future__ import annotations

# The fixed embedding vector dimension used in the photo_embeddings table.
# All services that generate or query embeddings must use this constant.
# Schema: photo_embeddings.embedding Vector(DB_EMBEDDING_DIMENSION)
DB_EMBEDDING_DIMENSION: int = 1024
