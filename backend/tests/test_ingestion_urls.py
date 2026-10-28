"""Unit tests for repository URL, commit SHA, and archive URL validation (#21)."""

import pytest

from repolens.ingestion import (
    InvalidCommitShaError,
    InvalidRepoUrlError,
    RepoCoordinate,
    UnsupportedHostError,
    build_archive_url,
    normalize_commit_sha,
    parse_repo_url,
)


VALID_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://github.com/octocat/hello-world",
        "https://github.com/octocat/hello-world/",
        "https://github.com/octocat/hello-world.git",
        "https://www.github.com/octocat/hello-world",
        "https://github.com:443/octocat/hello-world",
        "  https://github.com/octocat/hello-world  ",
        "https://GitHub.com/octocat/hello-world",
    ],
)
def test_parse_repo_url_accepts_supported_github_forms(raw_url: str) -> None:
    coordinate = parse_repo_url(raw_url)

    assert coordinate == RepoCoordinate(
        host="github.com", owner="octocat", name="hello-world"
    )
    assert coordinate.repo_url == "https://github.com/octocat/hello-world"


def test_parse_repo_url_preserves_owner_and_name_case() -> None:
    coordinate = parse_repo_url("https://github.com/OctoCat/Hello-World")

    assert coordinate.owner == "OctoCat"
    assert coordinate.name == "Hello-World"


@pytest.mark.parametrize(
    "raw_url",
    [
        "",
        "   ",
        "not a url",
        "github.com/octocat/hello-world",
        "https://github.com",
        "https://github.com/",
        "https://github.com/octocat",
        "https://github.com/octocat/",
        "https://github.com/octocat/hello-world/tree/main",
        "https://github.com/octocat/hello-world/blob/main/app.py",
        "https://github.com/octocat/hello world",
        "https://github.com/octocat/hello-world?download=1",
        "https://github.com/octocat/hello-world#readme",
        "https://github.com/../etc/passwd",
        "https://github.com/octocat/..",
        "https://user:token@github.com/octocat/hello-world",
        "https://github.com:8443/octocat/hello-world",
    ],
)
def test_parse_repo_url_rejects_invalid_urls(raw_url: str) -> None:
    with pytest.raises(InvalidRepoUrlError) as excinfo:
        parse_repo_url(raw_url)

    assert excinfo.value.code == "INVALID_URL"
    assert excinfo.value.message
    assert excinfo.value.hint


@pytest.mark.parametrize(
    "raw_url",
    [
        "http://github.com/octocat/hello-world",
        "git://github.com/octocat/hello-world",
        "ssh://git@github.com/octocat/hello-world",
        "file:///etc/passwd",
        "git@github.com:octocat/hello-world.git",
    ],
)
def test_parse_repo_url_rejects_non_https_schemes(raw_url: str) -> None:
    with pytest.raises(InvalidRepoUrlError) as excinfo:
        parse_repo_url(raw_url)

    assert excinfo.value.code == "INVALID_URL"
    assert "https" in excinfo.value.message.lower()


@pytest.mark.parametrize(
    "raw_url",
    [
        "https://gitlab.com/octocat/hello-world",
        "https://bitbucket.org/octocat/hello-world",
        "https://codeload.github.com/octocat/hello-world",
        "https://github.com.evil.example/octocat/hello-world",
        "https://evilgithub.com/octocat/hello-world",
        "https://raw.githubusercontent.com/octocat/hello-world",
        "https://127.0.0.1/octocat/hello-world",
    ],
)
def test_parse_repo_url_rejects_unsupported_hosts(raw_url: str) -> None:
    with pytest.raises(UnsupportedHostError) as excinfo:
        parse_repo_url(raw_url)

    assert excinfo.value.code == "UNSUPPORTED_HOST"
    assert "GitHub" in excinfo.value.message
    assert excinfo.value.hint


def test_unsupported_host_error_is_an_invalid_url_error() -> None:
    """Callers that only care about rejection can catch one error type."""
    with pytest.raises(InvalidRepoUrlError):
        parse_repo_url("https://gitlab.com/octocat/hello-world")


def test_ingestion_errors_serialize_to_the_api_error_shape() -> None:
    with pytest.raises(UnsupportedHostError) as excinfo:
        parse_repo_url("https://gitlab.com/octocat/hello-world")

    assert excinfo.value.to_dict() == {
        "code": excinfo.value.code,
        "message": excinfo.value.message,
        "hint": excinfo.value.hint,
    }


@pytest.mark.parametrize(
    "raw_sha, expected",
    [
        (VALID_SHA, VALID_SHA),
        (VALID_SHA.upper(), VALID_SHA),
        (f"  {VALID_SHA}  ", VALID_SHA),
    ],
)
def test_normalize_commit_sha_lowercases_full_shas(raw_sha: str, expected: str) -> None:
    assert normalize_commit_sha(raw_sha) == expected


@pytest.mark.parametrize(
    "raw_sha",
    [
        "",
        "   ",
        "main",
        "HEAD",
        "0123456",
        VALID_SHA[:39],
        VALID_SHA + "0",
        VALID_SHA[:-1] + "g",
        f"{VALID_SHA}/../../etc",
        "v1.0.0",
    ],
)
def test_normalize_commit_sha_rejects_anything_but_a_full_sha(raw_sha: str) -> None:
    with pytest.raises(InvalidCommitShaError) as excinfo:
        normalize_commit_sha(raw_sha)

    assert excinfo.value.code == "INVALID_SHA"
    assert excinfo.value.hint


def test_build_archive_url_pins_the_commit_on_the_github_archive_host() -> None:
    coordinate = parse_repo_url("https://github.com/octocat/hello-world")

    url = build_archive_url(coordinate, VALID_SHA)

    assert url == (
        f"https://codeload.github.com/octocat/hello-world/zip/{VALID_SHA}"
    )


def test_build_archive_url_validates_the_sha() -> None:
    coordinate = parse_repo_url("https://github.com/octocat/hello-world")

    with pytest.raises(InvalidCommitShaError):
        build_archive_url(coordinate, "main")
