from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from azure.core import MatchConditions
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from core.storage import Busy, LeaseGuard, Store, Superseded


def bare_store():
    return object.__new__(Store)


def test_source_download_requires_current_etag_and_enforces_size_limit(ref):
    storage = bare_store()
    blob = Mock()
    blob.get_blob_properties.return_value = SimpleNamespace(etag="v1", size=4)
    blob.download_blob.return_value.readall.return_value = b"data"
    storage.source = lambda _: blob
    assert storage.source_bytes(ref, 10) == b"data"
    assert blob.download_blob.call_args.kwargs == {
        "etag": "v1",
        "match_condition": MatchConditions.IfNotModified,
        "max_concurrency": 1,
    }
    with pytest.raises(ValueError):
        storage.source_bytes(ref, 3)
    blob.get_blob_properties.return_value.etag = "new"
    with pytest.raises(Superseded):
        storage.source_bytes(ref, 10)


def test_source_update_during_download_is_superseded(ref):
    storage = bare_store()
    blob = Mock()
    blob.get_blob_properties.return_value = SimpleNamespace(etag="v1", size=4)
    error = HttpResponseError()
    error.status_code = 412
    blob.download_blob.side_effect = error
    storage.source = lambda _: blob
    with pytest.raises(Superseded):
        storage.source_bytes(ref, 10)


def test_missing_source_is_not_a_storage_failure(ref):
    storage = bare_store()
    storage.source = lambda _: SimpleNamespace(get_blob_properties=Mock(side_effect=ResourceNotFoundError()))
    assert storage.current(ref) is None


def test_document_lease_is_released_on_failure():
    storage = bare_store()
    blob, lease = Mock(), Mock()
    blob.acquire_lease.return_value = lease
    storage.service = SimpleNamespace(get_blob_client=lambda *_: blob)
    with pytest.raises(ValueError), storage.lock("document"):
        raise ValueError("simulated failure")
    lease.release.assert_called_once()
    blob.acquire_lease.assert_called_once_with(lease_duration=60)


def test_busy_document_is_retryable():
    storage = bare_store()
    error = HttpResponseError()
    error.status_code = 409
    blob = Mock()
    blob.acquire_lease.side_effect = error
    storage.service = SimpleNamespace(get_blob_client=lambda *_: blob)
    with pytest.raises(Busy), storage.lock("document"):
        pytest.fail("Must not enter a leased document")


def test_lost_lease_fails_before_publication_continues():
    guard = LeaseGuard(Mock())
    guard.lost.set()
    with pytest.raises(Busy):
        guard.check()


def test_blocked_renewal_cannot_leave_a_guard_valid_past_its_deadline():
    guard = LeaseGuard(Mock())
    guard.last_renewed -= 46
    with pytest.raises(Busy):
        guard.check()


def test_lease_renewal_failure_marks_guard_lost():
    guard = LeaseGuard(SimpleNamespace(renew=Mock(side_effect=HttpResponseError())))
    guard.stopped = SimpleNamespace(wait=lambda _: False)
    guard.renew()
    with pytest.raises(Busy):
        guard.check()
