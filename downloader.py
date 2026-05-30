"""
Production-quality async download engine.

Features:
  - Cooperative pause/cancel via asyncio.Event (NO future.cancel())
  - 64 concurrent connections by default, configurable up to 128
  - Auto-retry with exponential backoff (max 10 retries per part)
  - Periodic metadata saves every 5 seconds during download
  - Async HEAD request via aiohttp (no synchronous requests)
  - Connection keep-alive with DNS caching
  - 16 KB chunk reads for optimal throughput
  - Thread-safe downloaded_bytes counter (atomic via threading.Lock)
  - Proper speed monitoring with ETA in a daemon thread
  - Crash recovery from saved .meta files
  - Global speed limiter shared across all connections
"""

import os
import sys
import time
import json
import math
import asyncio
import aiohttp
import aiofiles
import threading
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------------------
# Global daemon event-loop - one per process, shared by all DownloadJob instances
# ---------------------------------------------------------------------------
_loop = None
_loop_thread = None
_loop_lock = threading.Lock()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

CHUNK_SIZE = 16_384          # 16 KB per read
META_SAVE_INTERVAL = 5.0     # seconds between periodic metadata saves
MAX_RETRIES = 10             # retries per part
BASE_RETRY_DELAY = 1.0       # initial backoff delay in seconds
MAX_RETRY_DELAY = 60.0       # cap on exponential backoff
DEFAULT_THREADS = 64
MAX_THREADS = 128
REQUEST_TIMEOUT = aiohttp.ClientTimeout(
    total=None,
    connect=30,
    sock_connect=30,
    sock_read=60,
)


def get_event_loop():
    """Return the shared daemon event-loop, creating it on first call."""
    global _loop, _loop_thread
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            _loop_thread = threading.Thread(
                target=_loop.run_forever, daemon=True, name="dl-event-loop"
            )
            _loop_thread.start()
    return _loop


# ---------------------------------------------------------------------------
# AsyncSpeedLimiter - token-bucket, shared across all connections of a job
# ---------------------------------------------------------------------------
class AsyncSpeedLimiter:
    """
    A token-bucket speed limiter that operates inside the async event loop.
    All download coroutines of a single DownloadJob share one instance so
    the aggregate bandwidth is capped at limit bytes/sec.
    """

    def __init__(self, limit_bytes_sec=None):
        self.limit = limit_bytes_sec
        self._tokens = 0.0
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def update_limit(self, new_limit):
        """Thread-safe update of the speed cap (called from the GUI thread)."""
        self.limit = new_limit
        self._tokens = 0.0
        self._last_refill = time.monotonic()

    async def throttle(self, nbytes: int):
        """Block the caller until nbytes worth of tokens are available."""
        if not self.limit or self.limit <= 0:
            return

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens += elapsed * self.limit
            if self._tokens > self.limit:
                self._tokens = float(self.limit)
            self._last_refill = now

            self._tokens -= nbytes
            if self._tokens < 0:
                sleep_for = (-self._tokens) / self.limit
                await asyncio.sleep(sleep_for)
                self._tokens = 0.0
                self._last_refill = time.monotonic()


# ---------------------------------------------------------------------------
# DownloadJob - the main public class
# ---------------------------------------------------------------------------
class DownloadJob:
    """
    Manages the full lifecycle of a single file download.
    """

    def __init__(self, url, dest_path, num_threads=DEFAULT_THREADS, speed_limit=None):
        self.url = url
        self.dest_path = os.path.abspath(dest_path)
        self.meta_path = self.dest_path + ".meta"
        self.num_threads = min(max(1, num_threads), MAX_THREADS)
        self.speed_limit = speed_limit

        # -- state -----------------------------------------------------------
        self.total_size = 0
        self.downloaded_bytes = 0
        self.status = "Queued"
        self.error_message = ""

        self.supports_resume = False
        self.parts = []

        # -- async machinery -------------------------------------------------
        self.loop = get_event_loop()
        self.future = None
        self.stop_event = asyncio.Event()
        self.limiter = AsyncSpeedLimiter(self.speed_limit)
        self._meta_save_task = None

        # -- speed monitoring ------------------------------------------------
        self.start_time = 0.0
        self.current_speed = 0
        self.eta = 0.0
        self.monitor_active = False

        # -- thread-safe byte counter ---------------------------------------
        self._bytes_lock = threading.Lock()
        self._last_speed_bytes = 0
        self._last_speed_time = 0.0

    # -----------------------------------------------------------------------
    # Public helpers
    # -----------------------------------------------------------------------
    def get_filename_from_url(self):
        """Extract a human-readable filename from the URL path."""
        try:
            parsed = urlparse(self.url)
            filename = os.path.basename(parsed.path)
            if not filename or filename == "/":
                filename = "downloaded_file"
            return unquote(filename)
        except Exception:
            return "downloaded_file"

    # -----------------------------------------------------------------------
    # Initialization - async HEAD via aiohttp, with fallback
    # -----------------------------------------------------------------------
    def initialize(self):
        """
        Fetch remote headers and prepare chunk layout.
        Returns True on success, False on failure.
        """
        # --- attempt crash recovery from saved metadata --------------------
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, "r") as f:
                    meta = json.load(f)
                self.url = meta.get("url", self.url)
                self.total_size = meta.get("total_size", 0)
                self.supports_resume = meta.get("supports_resume", False)
                self.parts = meta.get("parts", [])
                if self.parts:
                    self.num_threads = len(self.parts)
                self.downloaded_bytes = sum(
                    p["current"] - p["start"] for p in self.parts
                )
                self.status = "Paused"
                return True
            except Exception as exc:
                print(f"[Downloader] Corrupt metadata, resetting: {exc}")
                try:
                    os.remove(self.meta_path)
                except OSError:
                    pass

        # --- fresh initialisation via async HEAD request -------------------
        try:
            result = asyncio.run_coroutine_threadsafe(
                self._async_initialize(), self.loop
            ).result(timeout=30)
            return result
        except Exception as exc:
            self.status = "Failed"
            self.error_message = str(exc)
            return False

    async def _async_initialize(self):
        """Perform an async HEAD (with GET fallback) to learn about the file."""
        headers = {"User-Agent": USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=20, connect=10)

        conn = aiohttp.TCPConnector(
            limit=4, ttl_dns_cache=300, enable_cleanup_closed=True
        )
        async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
            resolved_url = self.url
            status = 0
            resp_headers = {}
            try:
                # Use a fast 2.5-second timeout for HEAD; if it hangs, we fall back to GET immediately.
                async with session.head(
                    self.url,
                    headers=headers,
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=2.5, connect=2.0),
                ) as resp:
                    status = resp.status
                    resp_headers = resp.headers
                    resolved_url = str(resp.url)
            except Exception:
                status = 0

            if status == 0 or status >= 400:
                try:
                    async with session.get(
                        self.url, headers=headers, allow_redirects=True
                    ) as resp:
                        status = resp.status
                        resp_headers = resp.headers
                        resolved_url = str(resp.url)
                except Exception as exc:
                    raise RuntimeError(f"Cannot reach URL: {exc}") from exc

            if status >= 400:
                raise RuntimeError(f"Server returned HTTP {status}")

            self.url = resolved_url
            self.total_size = int(resp_headers.get("content-length", 0))
            accept_ranges = resp_headers.get("accept-ranges", "").lower()
            self.supports_resume = (
                accept_ranges == "bytes"
                or resp_headers.get("content-range") is not None
            )

            if self.total_size > 0 and not self.supports_resume:
                try:
                    probe_hdrs = {**headers, "Range": "bytes=0-0"}
                    async with session.get(
                        self.url, headers=probe_hdrs, allow_redirects=True
                    ) as resp:
                        if resp.status == 206:
                            self.supports_resume = True
                except Exception:
                    pass

        dir_name = os.path.dirname(self.dest_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        if self.total_size > 0 and self.supports_resume:
            with open(self.dest_path, "wb") as f:
                f.truncate(self.total_size)

            chunk_size = math.ceil(self.total_size / self.num_threads)
            self.parts = []
            for i in range(self.num_threads):
                start = i * chunk_size
                end = min(self.total_size - 1, (i + 1) * chunk_size - 1)
                if start > self.total_size - 1:
                    break
                self.parts.append({
                    "start": start,
                    "end": end,
                    "current": start,
                    "completed": False,
                })
            self.num_threads = len(self.parts)
        else:
            self.supports_resume = False
            self.num_threads = 1
            self.parts = [{
                "start": 0,
                "end": -1,
                "current": 0,
                "completed": False,
            }]

        self.save_metadata()
        return True

    # -----------------------------------------------------------------------
    # Metadata persistence
    # -----------------------------------------------------------------------
    def save_metadata(self):
        """Synchronously persist download state to disk."""
        if not self.supports_resume:
            return
        try:
            meta = {
                "url": self.url,
                "total_size": self.total_size,
                "supports_resume": self.supports_resume,
                "parts": self.parts,
            }
            tmp_path = self.meta_path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(meta, f)
            if os.path.exists(self.meta_path):
                os.replace(tmp_path, self.meta_path)
            else:
                os.rename(tmp_path, self.meta_path)
        except Exception as exc:
            print(f"[Downloader] Error saving metadata: {exc}")

    # -----------------------------------------------------------------------
    # Start / Pause / Cancel
    # -----------------------------------------------------------------------
    def start(self):
        """Begin (or resume) downloading."""
        if self.status == "Downloading":
            return

        self.status = "Downloading"
        self.error_message = ""
        self.start_time = time.time()

        with self._bytes_lock:
            self._last_speed_bytes = self.downloaded_bytes
            self._last_speed_time = time.time()

        self.monitor_active = True
        threading.Thread(
            target=self._monitor_speed, daemon=True, name="dl-speed-monitor"
        ).start()

        self.future = asyncio.run_coroutine_threadsafe(
            self._download_coordinator(), self.loop
        )

    def pause(self):
        """
        Cooperatively pause all connections. Sets the stop_event so every
        download coroutine will exit at the next chunk boundary.
        Does NOT use future.cancel().
        """
        if self.status != "Downloading":
            return
        self.status = "Paused"
        self.monitor_active = False
        self.current_speed = 0

        self.loop.call_soon_threadsafe(self.stop_event.set)
        self.save_metadata()

    def cancel(self):
        """Stop downloading and delete partially downloaded files."""
        self.status = "Paused"
        self.monitor_active = False
        self.current_speed = 0

        self.loop.call_soon_threadsafe(self.stop_event.set)

        for path in (self.meta_path, self.dest_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        self.downloaded_bytes = 0
        self.parts = []
        self.status = "Queued"

    def update_speed_limit(self, new_limit):
        """Update the speed cap at runtime (thread-safe)."""
        self.speed_limit = new_limit
        self.limiter.update_limit(new_limit)

    # -----------------------------------------------------------------------
    # Speed monitoring (runs in a daemon thread)
    # -----------------------------------------------------------------------
    def _monitor_speed(self):
        """Compute current_speed and eta once per second."""
        while self.monitor_active and self.status == "Downloading":
            time.sleep(1.0)
            now = time.time()
            with self._bytes_lock:
                current_bytes = self.downloaded_bytes
                elapsed = now - self._last_speed_time
                if elapsed <= 0.05:
                    continue
                delta = current_bytes - self._last_speed_bytes
                self.current_speed = max(0, int(delta / elapsed))
                self._last_speed_bytes = current_bytes
                self._last_speed_time = now

            if self.total_size > 0:
                remaining = self.total_size - current_bytes
                if self.current_speed > 0:
                    self.eta = remaining / self.current_speed
                else:
                    self.eta = 999_999
            else:
                self.eta = 0

    # -----------------------------------------------------------------------
    # Thread-safe byte accounting
    # -----------------------------------------------------------------------
    def _add_bytes(self, n):
        with self._bytes_lock:
            self.downloaded_bytes += n

    # -----------------------------------------------------------------------
    # Async download coordinator
    # -----------------------------------------------------------------------
    async def _download_coordinator(self):
        """
        Top-level coroutine that owns the aiohttp session, spawns per-part
        download tasks, runs the periodic metadata saver, and handles
        completion / failure.
        """
        self.stop_event.clear()
        self.limiter.update_limit(self.speed_limit)

        connector = aiohttp.TCPConnector(
            limit=self.num_threads + 10,
            limit_per_host=self.num_threads + 10,
            ttl_dns_cache=600,
            enable_cleanup_closed=True,
            keepalive_timeout=30,
        )

        async with aiohttp.ClientSession(
            connector=connector, timeout=REQUEST_TIMEOUT
        ) as session:
            self._meta_save_task = asyncio.ensure_future(
                self._periodic_meta_saver()
            )
            try:
                if self.supports_resume and len(self.parts) > 1:
                    tasks = [
                        asyncio.ensure_future(
                            self._download_part(session, idx)
                        )
                        for idx in range(len(self.parts))
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    errors = [r for r in results if isinstance(r, Exception)]
                    if errors and not self.stop_event.is_set():
                        raise errors[0]
                else:
                    await self._download_single_stream(session)

                if not self.stop_event.is_set() and self.status == "Downloading":
                    all_done = all(p["completed"] for p in self.parts)
                    if all_done:
                        self.status = "Completed"
                        self.current_speed = 0
                        self.eta = 0
                        if self.total_size > 0:
                            with self._bytes_lock:
                                self.downloaded_bytes = self.total_size
                        if os.path.exists(self.meta_path):
                            try:
                                os.remove(self.meta_path)
                            except OSError:
                                pass

            except asyncio.CancelledError:
                if self.status == "Downloading":
                    self.status = "Paused"
            except Exception as exc:
                if self.status == "Downloading":
                    self.status = "Failed"
                    self.error_message = str(exc)
                    print(f"[Downloader] Coordinator error: {exc}")
            finally:
                self.monitor_active = False
                if self._meta_save_task and not self._meta_save_task.done():
                    self._meta_save_task.cancel()
                    try:
                        await self._meta_save_task
                    except asyncio.CancelledError:
                        pass
                self.save_metadata()

    # -----------------------------------------------------------------------
    # Per-part download with auto-retry and exponential backoff
    # -----------------------------------------------------------------------
    async def _download_part(self, session, idx):
        """Download a single byte-range part with retry logic."""
        part = self.parts[idx]
        if part["completed"]:
            return

        headers = {"User-Agent": USER_AGENT}

        for attempt in range(MAX_RETRIES):
            if self.stop_event.is_set():
                return
            if self.status != "Downloading":
                return

            start_pos = part["current"]
            end_pos = part["end"]

            if start_pos > end_pos:
                part["completed"] = True
                return

            headers["Range"] = f"bytes={start_pos}-{end_pos}"

            try:
                async with session.get(
                    self.url, headers=headers, timeout=REQUEST_TIMEOUT
                ) as resp:
                    if resp.status not in (200, 206):
                        raise aiohttp.ClientError(
                            f"HTTP {resp.status} for part {idx}"
                        )

                    async with aiofiles.open(self.dest_path, mode="r+b") as f:
                        await f.seek(start_pos)

                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            if self.stop_event.is_set():
                                return
                            if not chunk:
                                continue

                            await f.write(chunk)
                            n = len(chunk)
                            start_pos += n
                            part["current"] = start_pos
                            self._add_bytes(n)

                            await self.limiter.throttle(n)

                part["completed"] = True
                return

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                print(
                    f"[Downloader] Part {idx} attempt {attempt + 1}/{MAX_RETRIES} "
                    f"failed: {exc}"
                )
                if self.stop_event.is_set():
                    return
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Part {idx} failed after {MAX_RETRIES} retries: {exc}"
                    ) from exc

                delay = min(BASE_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if self.stop_event.is_set():
                        return
                    await asyncio.sleep(min(0.5, deadline - time.monotonic()))

    # -----------------------------------------------------------------------
    # Single-stream download (no Range support / unknown size)
    # -----------------------------------------------------------------------
    async def _download_single_stream(self, session):
        """Download the entire file as a single stream."""
        headers = {"User-Agent": USER_AGENT}
        part = self.parts[0]

        for attempt in range(MAX_RETRIES):
            if self.stop_event.is_set():
                return
            if self.status != "Downloading":
                return

            try:
                async with session.get(
                    self.url, headers=headers, timeout=REQUEST_TIMEOUT
                ) as resp:
                    if resp.status >= 400:
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                    if self.total_size == 0:
                        cl = resp.headers.get("content-length")
                        if cl:
                            self.total_size = int(cl)

                    async with aiofiles.open(self.dest_path, mode="wb") as f:
                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            if self.stop_event.is_set():
                                return
                            if not chunk:
                                continue

                            await f.write(chunk)
                            n = len(chunk)
                            part["current"] += n
                            self._add_bytes(n)
                            await self.limiter.throttle(n)

                part["completed"] = True
                return

            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                print(
                    f"[Downloader] Stream attempt {attempt + 1}/{MAX_RETRIES} "
                    f"failed: {exc}"
                )
                if self.stop_event.is_set():
                    return
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Stream download failed after {MAX_RETRIES} retries: {exc}"
                    ) from exc

                delay = min(BASE_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if self.stop_event.is_set():
                        return
                    await asyncio.sleep(min(0.5, deadline - time.monotonic()))

    # -----------------------------------------------------------------------
    # Periodic metadata saver (runs as a background asyncio task)
    # -----------------------------------------------------------------------
    async def _periodic_meta_saver(self):
        """Save metadata to disk every META_SAVE_INTERVAL seconds."""
        try:
            while True:
                await asyncio.sleep(META_SAVE_INTERVAL)
                if self.stop_event.is_set():
                    break
                if self.status != "Downloading":
                    break
                await asyncio.get_event_loop().run_in_executor(
                    None, self.save_metadata
                )
        except asyncio.CancelledError:
            pass
