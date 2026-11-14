import importlib.util
from pathlib import Path


def module(path):
    spec = importlib.util.spec_from_file_location("tool", Path(__file__).parents[2] / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_retrieval_scores_deduplicate_chunks_at_document_grain():
    scores = module("scripts/evaluation/evaluate.py").scores
    value = scores(
        [{"sourcefile": "a"}, {"sourcefile": "a"}, {"sourcefile": "irrelevant"}, {"sourcefile": "b"}],
        {"a", "b"},
        2,
    )
    assert value["recall_at_k"] == 0.5
    assert value["mrr"] == 1
    assert 0 < value["ndcg_at_k"] < 1


def test_backend_benchmark_never_modifies_source_host_configuration():
    helper = module("scripts/select_backend.py")
    storage = helper.host_configuration("storage")
    scheduler = helper.host_configuration("scheduler")
    assert "storageProvider" not in storage["extensions"]["durableTask"]
    assert scheduler["extensions"]["durableTask"]["storageProvider"]["type"] == "azureManaged"
