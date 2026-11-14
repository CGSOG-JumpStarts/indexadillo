import inspect
from collections import deque

from orchestrators.index import index, index_document


def generator(builder):
    wrapped = builder._function.get_user_function()
    return inspect.getclosurevars(wrapped).nonlocals["fn"]


class Context:
    def __init__(self, payload):
        self.payload = payload
        self.continuation = None
        self.status = None

    def get_input(self):
        return self.payload

    def call_activity_with_retry(self, name, retry, payload):
        assert retry.to_json()["maxNumberOfAttempts"] == 10
        return ("activity", name, payload)

    def call_sub_orchestrator(self, name, payload):
        return ("sub", name, payload)

    def task_all(self, tasks):
        return ("all", tasks)

    def set_custom_status(self, status):
        self.status = status

    def continue_as_new(self, payload):
        self.continuation = payload


def drive(iterator, handler):
    task = next(iterator)
    while True:
        try:
            try:
                value = handler(task)
            except RuntimeError as exc:
                task = iterator.throw(exc)
            else:
                task = iterator.send(value)
        except StopIteration as result:
            return result.value


def test_empty_prefix_does_not_skip_later_prefix_and_reconciliation_runs():
    context = Context({"scope": {"tenant_id": "a"}, "reconcile": True})
    pages = deque(
        [
            {"documents": [], "offset": 1, "token": None, "done": False},
            {"documents": [{"id": "document"}], "offset": 2, "token": None, "done": True},
            {"documents": [], "token": None, "done": True},
        ]
    )
    seen = []

    def handle(task):
        if task[0] == "all":
            return [{"status": "published"}]
        seen.append(task[1])
        return None if task[1] == "ensure_index_exists" else pages.popleft()

    result = drive(generator(index)(context), handle)
    assert seen == ["ensure_index_exists", "list_blobs_chunk", "list_blobs_chunk", "list_missing_documents"]
    assert result["published"] == 1 and result["failed"] == 0


def test_collection_checkpoints_after_bounded_pages():
    context = Context({"scope": {"tenant_id": "a"}})
    number = 0

    def handle(task):
        nonlocal number
        if task[1] == "ensure_index_exists":
            return None
        number += 1
        return {"documents": [], "offset": number, "token": str(number), "done": False}

    drive(generator(index)(context), handle)
    assert context.continuation["offset"] == 25
    assert context.continuation["token"] == "25"


def test_document_failure_is_recorded_without_aborting_collection(ref):
    context = Context(ref)
    called = []

    def handle(task):
        called.append(task[1])
        if task[1] == "embedding":
            raise RuntimeError("downstream failure")
        return ref

    assert drive(generator(index_document)(context), handle) == {"status": "failed"}
    assert called[-1] == "record_document_failure"


def test_stale_document_stops_before_embedding_and_publication(ref):
    called = []

    def handle(task):
        called.append(task[1])
        return {**ref, "superseded": True}

    assert drive(generator(index_document)(Context(ref)), handle) == {"status": "superseded"}
    assert called == ["ensure_index_exists", "document_cracking"]
