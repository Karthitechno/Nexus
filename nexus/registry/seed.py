"""Seed script to initialize registry with verified PayPal tools."""
import json
from pathlib import Path
from nexus.registry.repository import JsonToolRepository
from nexus.registry.importer import PostmanImporter
from nexus.registry.enricher import ToolEnricher


def seed_registry(repo_path: str = "data/registry/tools.json", force_reseed: bool = False):
    repo = JsonToolRepository(repo_path)
    if repo.count() > 0 and not force_reseed:
        return repo

    collection_file = Path("data/paypal_collection.json")
    if not collection_file.exists():
        return repo

    with open(collection_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    importer = PostmanImporter()
    raw_tools = importer.import_collection(data)

    enricher = ToolEnricher()
    enriched_tools = enricher.enrich_tools(raw_tools)

    for tool in enriched_tools:
        try:
            repo.create(tool)
        except ValueError:
            repo.update(tool)

    return repo


if __name__ == "__main__":
    r = seed_registry(force_reseed=True)
    print(f"Successfully seeded {r.count()} verified tools into registry.")

