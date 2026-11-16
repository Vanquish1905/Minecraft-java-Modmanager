"""Small HTTP layer built on urllib (no third-party dependencies)."""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import __version__, APP_ID

USER_AGENT = f"{APP_ID}/{__version__}"
TIMEOUT = 30


class NetworkError(Exception):
    pass


class Cancelled(Exception):
    pass


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:  # python.org builds on macOS ship without system certificates
        import certifi  # type: ignore

        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


_CTX = _ssl_context()


def _explain(err: Exception, url: str) -> NetworkError:
    msg = f"{url}: {err}"
    if isinstance(err, urllib.error.URLError) and isinstance(err.reason, ssl.SSLCertVerificationError):
        msg += ("\n\nSSL certificates could not be verified. On macOS run "
                "'Install Certificates.command' from your Python folder, or 'pip install certifi'.")
    return NetworkError(msg)


def request(url: str, data: bytes | None = None, headers: dict | None = None,
            method: str | None = None, timeout: int = TIMEOUT, retries: int = 2) -> bytes:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}
    if headers:
        hdrs.update(headers)
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = b""
            try:
                body = e.read()
            except Exception:
                pass
            if 500 <= e.code < 600 or e.code == 429:
                last = e
                time.sleep(1.5 * (attempt + 1))
                continue
            err = HTTPStatusError(e.code, url, body)
            raise err from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise _explain(last or Exception("unknown error"), url)


class HTTPStatusError(NetworkError):
    def __init__(self, code: int, url: str, body: bytes = b""):
        self.code = code
        self.url = url
        self.body = body
        super().__init__(f"HTTP {code} for {url}")

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8"))
        except Exception:
            return None


def get_json(url: str, params: dict | None = None, headers: dict | None = None):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    return json.loads(request(url, headers=headers).decode("utf-8"))


def post_json(url: str, payload, headers: dict | None = None):
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    body = request(url, data=json.dumps(payload).encode("utf-8"), headers=hdrs, method="POST", retries=0)
    return json.loads(body.decode("utf-8")) if body else None


def post_form(url: str, fields: dict, headers: dict | None = None):
    hdrs = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        hdrs.update(headers)
    body = request(url, data=urllib.parse.urlencode(fields).encode("utf-8"), headers=hdrs,
                   method="POST", retries=0)
    return json.loads(body.decode("utf-8")) if body else None


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def file_ok(path: Path, sha1: str | None = None, size: int | None = None) -> bool:
    if not path.is_file():
        return False
    if size is not None and size >= 0 and path.stat().st_size != size:
        return False
    if sha1:
        return sha1_of(path).lower() == sha1.lower()
    return True


def download(url: str, dest: Path, sha1: str | None = None, size: int | None = None,
             cancel: threading.Event | None = None) -> Path:
    """Download `url` to `dest` atomically, verifying the SHA-1 when known."""
    if file_ok(dest, sha1, size):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + f".part{threading.get_ident()}")
    last: Exception | None = None
    for attempt in range(3):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            h = hashlib.sha1()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as resp, open(tmp, "wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    h.update(chunk)
                    out.write(chunk)
            if sha1 and h.hexdigest().lower() != sha1.lower():
                raise NetworkError(f"Checksum mismatch for {url}")
            os.replace(tmp, dest)
            return dest
        except Cancelled:
            tmp.unlink(missing_ok=True)
            raise
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            if e.code == 404:
                raise HTTPStatusError(404, url) from None
            last = e
        except Exception as e:  # network hiccup or checksum problem: retry
            tmp.unlink(missing_ok=True)
            last = e
        time.sleep(1.0 * (attempt + 1))
    raise _explain(last or Exception("download failed"), url)


@dataclass
class DownloadJob:
    url: str
    dest: Path
    sha1: Optional[str] = None
    size: Optional[int] = None


ProgressFn = Callable[[str, Optional[float]], None]


def download_many(jobs: Iterable[DownloadJob], progress: ProgressFn | None = None,
                  label: str = "Downloading", workers: int = 8,
                  cancel: threading.Event | None = None) -> None:
    """Download many files in parallel, skipping ones that are already valid."""
    jobs = list(jobs)
    # Collapse duplicates (same destination).
    unique: dict[str, DownloadJob] = {}
    for j in jobs:
        unique.setdefault(str(j.dest), j)
    jobs = list(unique.values())
    total = len(jobs)
    if not total:
        return
    done = 0
    lock = threading.Lock()

    def work(job: DownloadJob):
        download(job.url, job.dest, job.sha1, job.size, cancel)

    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, j): j for j in jobs}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Cancelled:
                for f in futures:
                    f.cancel()
                raise
            except Exception as e:
                errors.append(str(e))
            with lock:
                done += 1
                if progress:
                    progress(f"{label} ({done}/{total})", done / total)
    if errors:
        more = f"\n...and {len(errors) - 5} more" if len(errors) > 5 else ""
        raise NetworkError(f"{len(errors)} download(s) failed:\n" + "\n".join(errors[:5]) + more)
