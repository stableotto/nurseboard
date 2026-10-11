"""Tests for saved-search webhook delivery. Run: python -m pytest tests/"""

import hashlib
import hmac
import json
from unittest import mock

import pipeline.notify_subscriptions as ns


class FakeKV:
    def __init__(self, items):
        self.items = items
        self.deleted = []
        self.puts = 0

    def keys(self, prefix):
        return [k for k in self.items if k.startswith(prefix)]

    def get(self, key):
        return self.items.get(key)

    def put(self, key, value):
        self.puts += 1
        self.items[key] = value

    def delete(self, key):
        self.deleted.append(key)
        self.items.pop(key, None)


def _sub(**kw):
    return {"id": "s1", "webhook_url": "https://hook.example/x", "query": {"role": "rn,lpn"},
            "secret": "k", "start_after": "2026-10-10T00:00:00+00:00", **kw}


def _page(jobs, next_offset=None, as_of="2026-10-11T00:00:00+00:00"):
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"results": jobs, "data_as_of": as_of, "next_offset": next_offset}
    resp.raise_for_status = lambda: None
    return resp


def _run(kv, pages, hook_status=200, public=True):
    posted = []

    def fake_post(url, data, headers, **_):
        posted.append((url, data, headers))
        return mock.Mock(status_code=hook_status)

    with mock.patch.object(ns, "KV", return_value=kv), \
         mock.patch.object(ns, "_kv_namespace_id", return_value="ns"), \
         mock.patch.object(ns, "public_host", return_value=public), \
         mock.patch.dict("os.environ", {"CLOUDFLARE_API_TOKEN": "t", "CLOUDFLARE_ACCOUNT_ID": "a"}), \
         mock.patch.object(ns.requests, "get", side_effect=pages) as get, \
         mock.patch.object(ns.requests, "post", side_effect=fake_post):
        ns.run()
    return posted, get


def test_delivers_all_pages_signed_and_advances_cursor():
    kv = FakeKV({"webhook:s1": _sub()})
    jobs = [{"id": f"j{i}"} for i in range(60)]
    posted, get = _run(kv, [_page(jobs[:50], next_offset=50), _page(jobs[50:])])
    first = get.call_args_list[0].kwargs["params"]
    assert first["first_seen_after"] == "2026-10-10T00:00:00+00:00" and first["role"] == "rn,lpn"
    assert get.call_args_list[1].kwargs["params"]["offset"] == 50
    assert [len(json.loads(body)["jobs"]) for _, body, _ in posted] == [50, 10]
    _, body, headers = posted[0]
    assert headers["X-ScrubShifts-Signature"] == "sha256=" + hmac.new(b"k", body, hashlib.sha256).hexdigest()
    assert kv.items["state:s1"]["cursor"] == "2026-10-11T00:00:00+00:00"
    assert kv.items["webhook:s1"] == _sub()  # the user's record is never rewritten


def test_idle_run_writes_nothing():
    kv = FakeKV({"webhook:s1": _sub(), "meta:webhook_count": 1})
    posted, _ = _run(kv, [_page([])])
    assert posted == [] and kv.puts == 0


def test_failed_delivery_keeps_cursor_then_removes_after_repeats():
    kv = FakeKV({"webhook:s1": _sub(), "meta:webhook_count": 1})
    _run(kv, [_page([{"id": "j1"}])], hook_status=500)
    assert kv.items["state:s1"] == {"cursor": "2026-10-10T00:00:00+00:00", "failures": 1}
    kv.items["state:s1"]["failures"] = ns.MAX_FAILURES - 1
    _run(kv, [_page([{"id": "j1"}])], hook_status=500)
    assert "webhook:s1" in kv.deleted and "state:s1" in kv.deleted
    assert kv.items["meta:webhook_count"] == 0


def test_private_webhook_host_is_not_contacted():
    kv = FakeKV({"webhook:s1": _sub()})
    posted, _ = _run(kv, [_page([{"id": "j1"}])], public=False)
    assert posted == [] and kv.items["state:s1"]["failures"] == 1


def test_deleted_subscription_is_not_resurrected():
    kv = FakeKV({"state:s1": {"cursor": "x", "failures": 0}})  # webhook:s1 deleted by the user
    posted, get = _run(kv, [])
    assert posted == [] and get.call_count == 0 and "webhook:s1" not in kv.items


def test_public_host_rejects_private_resolution():
    with mock.patch.object(ns.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("169.254.169.254", 443))]):
        assert not ns.public_host("https://metadata.example/x")
    with mock.patch.object(ns.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]):
        assert ns.public_host("https://example.com/x")
