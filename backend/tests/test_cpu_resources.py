import os

from repolens.search.embedding import FastEmbedEmbedder, effective_cpu_count


def reader(files: dict[str, str]):
    return lambda path: files.get(path)


def test_effective_cpu_count_honors_cgroup_v2_quota() -> None:
    count = effective_cpu_count(
        read_text=reader({"/sys/fs/cgroup/cpu.max": "150000 100000\n"}),
        affinity_count=8,
        host_count=16,
    )

    assert count == 2


def test_effective_cpu_count_honors_cgroup_v1_quota() -> None:
    count = effective_cpu_count(
        read_text=reader(
            {
                "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "100000\n",
                "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000\n",
            }
        ),
        affinity_count=8,
        host_count=16,
    )

    assert count == 1


def test_effective_cpu_count_uses_tightest_available_limit() -> None:
    count = effective_cpu_count(
        read_text=reader({"/sys/fs/cgroup/cpu.max": "max 100000\n"}),
        affinity_count=3,
        host_count=16,
    )

    assert count == 3


def test_effective_cpu_count_handles_platform_affinity(monkeypatch) -> None:
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 1, 2}, raising=False)
    assert effective_cpu_count(read_text=reader({}), host_count=8) == 3

    monkeypatch.delattr(os, "sched_getaffinity")
    assert effective_cpu_count(read_text=reader({}), host_count=8) == 8


def test_effective_cpu_count_handles_unavailable_affinity(monkeypatch) -> None:
    def unavailable(pid):
        raise OSError("affinity unavailable")

    monkeypatch.setattr(os, "sched_getaffinity", unavailable, raising=False)
    assert effective_cpu_count(read_text=reader({}), host_count=8) == 8


def test_fastembed_default_threads_are_bounded_by_effective_cpus(monkeypatch) -> None:
    monkeypatch.setattr("repolens.search.embedding.effective_cpu_count", lambda: 1)

    embedder = FastEmbedEmbedder()

    assert embedder.threads == 1
