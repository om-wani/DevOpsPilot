import pytest

import rate_limit


@pytest.fixture(autouse=True)
def clear():
    rate_limit.reset()
    yield
    rate_limit.reset()


def test_requests_under_the_limit_pass():
    for _ in range(20):
        rate_limit.check("user-1", now=100.0)


def test_the_request_past_the_limit_is_refused():
    for _ in range(20):
        rate_limit.check("user-1", now=100.0)
    with pytest.raises(rate_limit.RateLimited):
        rate_limit.check("user-1", now=100.0)


def test_remaining_allowance_counts_down():
    assert rate_limit.check("user-1", max_requests=3, now=100.0) == 2
    assert rate_limit.check("user-1", max_requests=3, now=100.0) == 1
    assert rate_limit.check("user-1", max_requests=3, now=100.0) == 0


def test_window_expiry_frees_the_allowance():
    for _ in range(20):
        rate_limit.check("user-1", now=100.0)
    # One second past the window, the earlier hits no longer count.
    rate_limit.check("user-1", now=161.0)


def test_window_slides_rather_than_resetting():
    for _ in range(20):
        rate_limit.check("user-1", now=100.0)
    # Still inside the window: refused.
    with pytest.raises(rate_limit.RateLimited):
        rate_limit.check("user-1", now=159.0)


def test_users_have_separate_allowances():
    for _ in range(20):
        rate_limit.check("user-1", now=100.0)
    rate_limit.check("user-2", now=100.0)


def test_retry_after_is_a_positive_whole_number():
    for _ in range(3):
        rate_limit.check("user-1", max_requests=3, now=100.0)
    with pytest.raises(rate_limit.RateLimited) as exc:
        rate_limit.check("user-1", max_requests=3, now=130.0)
    assert exc.value.retry_after > 0
    assert isinstance(exc.value.retry_after, int)
