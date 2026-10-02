from collector.http_client import PoliteHttpClient


def test_read_only_post_is_retryable() -> None:
    client = PoliteHttpClient(user_agent="test", timeout=1, delay=0, retries=3)
    retries = client.session.get_adapter("https://").max_retries
    assert retries.total == 3
    assert "POST" in retries.allowed_methods
    assert retries.backoff_factor == 1.0

