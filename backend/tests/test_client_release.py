"""Picking the newest Android app from GitHub releases."""
from app.services.client_release import pick

URL = "https://github.com/simplyzubair/unifierr/releases/download/client-v0.1.5/unifierr-android-arm64-preview-0.1.5.apk"


def test_picks_newest_client_release_with_an_apk():
    releases = [
        {"tag_name": "v9.9.9", "assets": [{"browser_download_url": URL}]},  # not a client release
        {"tag_name": "client-v0.1.6", "draft": True, "assets": [{"browser_download_url": URL}]},
        {"tag_name": "client-v0.1.5", "assets": [{"browser_download_url": "x.exe"}, {"browser_download_url": URL}]},
    ]
    assert pick(releases) == {"version": "0.1.5", "android_url": URL}


def test_ignores_apk_links_outside_this_repo():
    releases = [{"tag_name": "client-v0.2.0", "assets": [{"browser_download_url": "https://evil.example/a.apk"}]}]
    assert pick(releases) is None


async def test_needs_sign_in(client):
    assert (await client.get("/api/client/latest")).status_code == 401
