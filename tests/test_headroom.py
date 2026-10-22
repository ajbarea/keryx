import json
import subprocess

import pytest

from keryx.headroom import gpu_free_mb, low_memory, mem_available_mb, model_loaded


def test_mem_available_is_read_in_mb(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:  10485760 kB\nMemFree: 1 kB\nMemAvailable:    2097152 kB\n")
    assert mem_available_mb(meminfo) == 2048


@pytest.mark.parametrize("text", ["", "MemTotal: 5 kB\n", "MemAvailable: lots kB\n"])
def test_mem_available_is_none_without_a_usable_line(tmp_path, text):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(text)
    assert mem_available_mb(meminfo) is None


def test_mem_available_is_none_when_unreadable(tmp_path):
    assert mem_available_mb(tmp_path / "missing") is None


def _run_returning(stdout, returncode=0):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    return run, seen


def test_gpu_free_asks_nvidia_smi_with_a_timeout():
    run, seen = _run_returning("6891\n")
    assert gpu_free_mb(run) == 6891
    assert seen["cmd"] == [
        "nvidia-smi",
        "--query-gpu=memory.free",
        "--format=csv,noheader,nounits",
    ]
    assert seen["kw"]["timeout"] == 2


def test_gpu_free_reads_the_first_gpu_only():
    assert gpu_free_mb(_run_returning("6891\n20000\n")[0]) == 6891


@pytest.mark.parametrize("stdout", ["", "N/A\n", "[Not Supported]\n"])
def test_gpu_free_is_none_for_unparsable_output(stdout):
    assert gpu_free_mb(_run_returning(stdout)[0]) is None


def test_gpu_free_is_none_on_a_nonzero_exit():
    assert gpu_free_mb(_run_returning("6891\n", returncode=9)[0]) is None


@pytest.mark.parametrize(
    "exc", [FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 2), OSError("x")]
)
def test_gpu_free_is_none_when_the_probe_cannot_run(exc):
    def run(cmd, **kw):
        raise exc

    assert gpu_free_mb(run) is None


def _ps(*names):
    seen = []

    def fetch(url):
        seen.append(url)
        return json.dumps({"models": [{"name": n, "model": n} for n in names]}).encode()

    return fetch, seen


def test_model_loaded_when_listed():
    fetch, seen = _ps("gemma3:4b")
    assert model_loaded("http://h:1/", "gemma3:4b", fetch) is True
    assert seen == ["http://h:1/api/ps"]


def test_model_loaded_matches_the_latest_tag():
    assert model_loaded("http://h", "llama3", _ps("llama3:latest")[0]) is True


def test_model_not_loaded_when_another_is():
    assert model_loaded("http://h", "gemma3:4b", _ps("llama3:latest")[0]) is False
    assert model_loaded("http://h", "gemma3:4b", _ps()[0]) is False


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"models": 5}', b'{"models": [3]}'])
def test_model_loaded_false_for_a_malformed_answer(body):
    assert model_loaded("http://h", "m", lambda url: body) is False


def test_model_loaded_false_on_error():
    def fetch(url):
        raise OSError("refused")

    assert model_loaded("http://h", "m", fetch) is False


def test_low_ram_trips_alone():
    assert low_memory(2048, 4096, 1500, 9000) == "RAM 1500 MB free < 2048"


def test_low_vram_trips_alone():
    assert low_memory(2048, 4096, 9000, 2100) == "GPU 2100 MiB free < 4096"


def test_enough_of_both_is_not_low():
    assert low_memory(2048, 4096, 2048, 4096) is None


def test_a_probe_that_returned_none_never_trips():
    assert low_memory(2048, 4096, None, None) is None
    assert low_memory(2048, 4096, None, 100) == "GPU 100 MiB free < 4096"
    assert low_memory(2048, 4096, 100, None) == "RAM 100 MB free < 2048"


def test_a_zero_threshold_disables_its_check():
    assert low_memory(0, 4096, 1, 9000) is None
    assert low_memory(2048, 0, 9000, 1) is None
