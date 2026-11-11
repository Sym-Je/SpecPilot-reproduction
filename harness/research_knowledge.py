"""Read-only public knowledge for a trusted broker, never research-role code.

PublicKnowledge(record=trusted_call_record).search_public(query) and
read_public(url) return JSON-compatible receipts. Module-level equivalents take
the same trusted ``record`` keyword. Only the broker chooses the record directory,
timeout, DNS resolver and transport; none are accepted from research-role input.
dispatch_public(action, record) is the strict broker adapter: action contains only
kind plus query or url. It maps successful status to completed. audit_record(record)
reads receipts offline and verifies internal consistency, not network authenticity.
The transport contract is (url, validated_addresses, timeout, max_bytes) -> Response;
the resolver contract is (hostname, timeout) -> numeric IP addresses. Test hooks
are trusted dependencies, not options to expose through the shared broker.

All returned text and raw receipts are untrusted data, not instructions. No tools,
commands, credentials, cookies or authentication are used. Direct access remains
the default. Only the broker can explicitly install trusted_proxy_transport(),
which snapshots the existing HTTPS_PROXY/HTTP_PROXY configuration without ever
persisting its value. Only unauthenticated HTTP proxies are supported. CONNECT
uses the independently validated target IP, followed by TLS for the original host;
there is no hostname CONNECT fallback or proxy-side target DNS resolution.
Only textual public resources are supported; PDFs and compressed bodies fail
closed. Search uses the fixed, unauthenticated Bing RSS endpoint. Availability
is not guaranteed, and an empty, blocked or malformed response is unavailable.
"""

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import stat
import threading
import time
import unicodedata
from urllib.parse import unquote, urlencode, urljoin, urlsplit, urlunsplit
import uuid
import xml.etree.ElementTree as ElementTree


MAX_QUERY_CHARS = 240
MAX_CONTENT_BYTES = 24 * 1024
MAX_RAW_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
MAX_RESULTS = 8
SEARCH_URL = "https://www.bing.com/search"
SEARCH_HOSTS = frozenset({"www.bing.com", "cn.bing.com"})
PUBLIC_HOSTS = frozenset({
    "arxiv.org", "www.arxiv.org", "export.arxiv.org",
    "docs.nvidia.com", "developer.nvidia.com", "www.nvidia.com", "nvidia.github.io",
    "pytorch.org", "www.pytorch.org", "docs.pytorch.org",
    "triton-lang.org", "www.triton-lang.org",
    "docs.sglang.ai", "docs.sglang.io", "sglang.readthedocs.io",
    "github.com", "raw.githubusercontent.com",
})
_TEXT_TYPES = frozenset({
    "text/plain", "text/html", "text/markdown", "text/x-rst",
    "application/json", "application/xml", "text/xml",
    "application/rss+xml", "application/atom+xml",
})
_RESTRICTED = re.compile(
    r"(?:^|[^a-z0-9])(?:sealed|private|final|credentials?|secrets?|"
    r"restricted|controller|eval|ledger|logs|\.env|\.ssh|\.aws|\.git|\.netrc|"
    r"id_rsa|id_ed25519)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
_CREDENTIAL = re.compile(
    r"(?:authorization|proxy-authorization|bearer\s|"
    r"api[ _-]?key|password|passwd|access[ _-]?token|auth[ _-]?token|"
    r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret|token)\s*[:=]|"
    r"gh[pousr]_[a-z0-9]+|github_pat_[a-z0-9_]+|hf_[a-z0-9]{12,}|sk-[a-z0-9_-]{12,}|"
    r"AKIA[A-Z0-9]{16}|-----BEGIN|[a-z][a-z0-9+.-]*://[^/\s]*@)", re.IGNORECASE,
)
_WORKERS = threading.BoundedSemaphore(8)


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes
    truncated: bool = False
    header_bytes: int = 0
    wire_bytes: int = 0


class _Unavailable(Exception):
    pass


class _RawLimit(_Unavailable):
    pass


@dataclass(frozen=True, repr=False)
class _Proxy:
    host: str
    port: int


class _ProxyTransport:
    def __init__(self, proxy=None, error=None):
        self.proxy = proxy
        self.error = error

    def __call__(self, url, addresses, timeout, max_bytes):
        if self.error:
            raise _Unavailable(self.error)
        return https_get(url, addresses, timeout, max_bytes, _proxy=self.proxy)


def trusted_proxy_transport():
    """Broker-only opt-in transport from existing, credential-free HTTP proxy env.

    Snapshot precedence is HTTPS_PROXY, https_proxy, HTTP_PROXY, http_proxy. This
    function never enumerates the environment, reads credential files, changes
    environment variables, uses ALL_PROXY/NO_PROXY, or echoes proxy configuration.
    A missing/invalid/authenticated proxy becomes a bounded unavailable receipt
    when this transport is passed to dispatch_public; it never falls back to a
    different proxy, target-hostname CONNECT, or insecure TLS. Trusted proxy
    infrastructure may be private; target addresses must still all be public.
    """
    value = None
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.environ.get(name)
        if value:
            break
    if not value:
        return _ProxyTransport(error="proxy_not_configured")
    try:
        if len(value) > 2048 or not value.isascii() or any(character.isspace() for character in value):
            raise ValueError
        if "@" in value:
            return _ProxyTransport(error="proxy_authentication_not_supported")
        parts = urlsplit(value)
        if (parts.scheme != "http" or parts.path not in {"", "/"} or parts.query or parts.fragment
                or "\\" in value or not parts.hostname or "%" in parts.hostname):
            raise ValueError
        host = parts.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
                raise ValueError from None
        port = parts.port if parts.port is not None else 80
        if not 1 <= port <= 65535:
            raise ValueError
        return _ProxyTransport(proxy=_Proxy(host, port))
    except (TypeError, ValueError):
        return _ProxyTransport(error="proxy_configuration_not_supported")


def _decoded(value):
    decoded = unicodedata.normalize("NFKC", value)
    for unused in range(4):
        expanded = unquote(decoded)
        if expanded == decoded:
            break
        decoded = expanded
    if "%" in decoded or any(ord(character) < 32 or ord(character) == 127 for character in decoded):
        raise _Unavailable("unsafe_input")
    return decoded


def _sensitive(value):
    folded = value.casefold()
    return (
        "specpilot" in re.sub(r"[^a-z0-9]", "", folded)
        or _RESTRICTED.search(folded)
        or _CREDENTIAL.search(value)
    )


def _query(value):
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_QUERY_CHARS or not value.strip():
        raise _Unavailable("invalid_query_length")
    decoded = _decoded(value)
    if _sensitive(decoded) or any(character in decoded for character in "/\\$`|;&<>~"):
        raise _Unavailable("query_not_public_or_unsafe")
    if re.search(r"(?:^|\s)(?:[A-Za-z]:|\.{1,2}(?:\s|$))", decoded):
        raise _Unavailable("local_path_query")
    if re.match(r"\s*(?:sh|bash|zsh|sudo|env|printenv|export|source|curl|wget|cat|exec)\b", decoded):
        raise _Unavailable("shell_query")
    return value.strip()


def _url(value, provider=False):
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise _Unavailable("invalid_url")
    decoded = _decoded(value)
    if any(character.isspace() for character in value) or "\\" in decoded or _sensitive(decoded):
        raise _Unavailable("url_not_public_or_unsafe")
    try:
        parts = urlsplit(value)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise _Unavailable("invalid_url") from None
    if parts.scheme != "https" or port not in (None, 443) or parts.username is not None or parts.password is not None:
        raise _Unavailable("https_public_without_credentials_required")
    if not host or parts.fragment:
        raise _Unavailable("invalid_url")
    if provider:
        if host not in SEARCH_HOSTS or parts.path != "/search":
            raise _Unavailable("provider_redirect_not_allowed")
    elif host not in PUBLIC_HOSTS:
        raise _Unavailable("host_not_allowlisted")
    if host == "github.com" and (parts.path or "/").split("/")[1].lower() in {
        "login", "logout", "settings", "sessions", "notifications", "account", "user",
    }:
        raise _Unavailable("github_non_public_endpoint")
    return urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def resolve_public(host, timeout):
    """Resolve without reading proxy settings; the caller bounds DNS wall time."""
    return list(dict.fromkeys(
        answer[4][0] for answer in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ))


def _addresses(values):
    if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= 32:
        raise _Unavailable("invalid_dns_answers")
    checked = []
    for value in values:
        if not isinstance(value, str) or "%" in value:
            raise _Unavailable("invalid_dns_address")
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise _Unavailable("invalid_dns_address") from None
        if (not address.is_global or address.is_multicast or address.is_reserved
                or address.is_unspecified or address.is_loopback or address.is_link_local
                or getattr(address, "ipv4_mapped", None) is not None
                or getattr(address, "sixtofour", None) is not None
                or getattr(address, "teredo", None) is not None
                or (address.version == 6 and address not in ipaddress.ip_network("2000::/3"))):
            raise _Unavailable("non_public_dns_address")
        checked.append(str(address))
    return tuple(dict.fromkeys(checked))


def _bounded(function, timeout):
    if timeout <= 0 or not _WORKERS.acquire(blocking=False):
        raise _Unavailable("deadline_or_worker_limit")
    output = queue.Queue(maxsize=1)

    def run():
        try:
            output.put((True, function()))
        except _Unavailable as failure:
            output.put((False, str(failure)))
        except Exception:
            output.put((False, None))
        finally:
            _WORKERS.release()

    threading.Thread(target=run, daemon=True).start()
    try:
        successful, result = output.get(timeout=timeout)
    except queue.Empty:
        raise _Unavailable("network_timeout") from None
    if not successful:
        raise _Unavailable(result or "network_unavailable")
    return result


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout, proxy=None, max_bytes=MAX_RAW_BYTES):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.address = address
        self.raw_socket = None
        self.tls_socket = None
        self.cancelled = threading.Event()
        self.proxy = proxy
        self.max_bytes = max_bytes
        self.connect_bytes = 0

    def connect(self):
        if self.cancelled.is_set():
            raise _Unavailable("network_timeout")
        endpoint = (self.address, 443)
        family = socket.AF_INET6 if ":" in self.address else socket.AF_INET
        if self.proxy is not None:
            answers = socket.getaddrinfo(self.proxy.host, self.proxy.port, type=socket.SOCK_STREAM)
            if not answers:
                raise _Unavailable("proxy_dns_unavailable")
            numeric = ipaddress.ip_address(answers[0][4][0])
            family = socket.AF_INET6 if numeric.version == 6 else socket.AF_INET
            endpoint = (str(numeric), self.proxy.port)
        raw_socket = socket.socket(family, socket.SOCK_STREAM)
        self.raw_socket = raw_socket
        if self.cancelled.is_set():
            raw_socket.close()
            raise _Unavailable("network_timeout")
        raw_socket.settimeout(self.timeout)
        raw_socket.connect(endpoint)
        if self.proxy is not None:
            self._connect_tunnel(raw_socket)
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except ssl.SSLCertVerificationError:
            raise _Unavailable("tls_certificate_verification_failed") from None
        except ssl.SSLError:
            raise _Unavailable("tls_handshake_failed") from None
        self.tls_socket = self.sock
        if self.cancelled.is_set():
            self.abort()
            raise _Unavailable("network_timeout")

    def _connect_tunnel(self, raw_socket):
        address = "[" + self.address + "]" if ":" in self.address else self.address
        authority = address + ":443"
        raw_socket.sendall(("CONNECT " + authority + " HTTP/1.1\r\nHost: " + authority + "\r\n\r\n").encode("ascii"))
        response = _LimitedResponse(raw_socket, method="CONNECT", max_bytes=min(16384, self.max_bytes))
        try:
            try:
                response.begin()
            except _RawLimit:
                raise _Unavailable("proxy_connect_response_limit") from None
            self.connect_bytes = response.header_bytes
            if response.status != 200:
                raise _Unavailable("proxy_connect_rejected_" + str(response.status))
            if self.connect_bytes >= self.max_bytes:
                raise _Unavailable("proxy_connect_response_limit")
        finally:
            response.close()

    def abort(self):
        self.cancelled.set()
        for connection in (self.tls_socket, self.raw_socket):
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except (OSError, AttributeError):
                    pass
                connection.close()


class _HeaderBudget:
    def __init__(self, source, limit):
        self.source = source
        self.limit = limit
        self.used = 0

    def readline(self, size=-1):
        remaining = self.limit - self.used
        if remaining <= 0:
            raise _RawLimit("raw_response_limit")
        line = self.source.readline(min(size, remaining) if size >= 0 else remaining)
        self.used += len(line)
        if self.used == self.limit and not line.endswith(b"\n"):
            raise _RawLimit("raw_response_limit")
        return line

    def _read(self, method, size):
        remaining = self.limit - self.used
        if remaining <= 0:
            raise _RawLimit("raw_response_limit")
        data = method(min(size, remaining) if size >= 0 else remaining)
        self.used += len(data)
        return data

    def read(self, size=-1):
        return self._read(self.source.read, size)

    def read1(self, size=-1):
        return self._read(self.source.read1, size)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def __getattr__(self, name):
        return getattr(self.source, name)


class _LimitedResponse(http.client.HTTPResponse):
    def __init__(self, *args, max_bytes, **kwargs):
        super().__init__(*args, **kwargs)
        self.fp = _HeaderBudget(self.fp, max_bytes)
        self.raw_reader = self.fp
        self.header_bytes = 0

    def begin(self):
        super().begin()
        self.header_bytes = self.fp.used


def https_get(url, addresses, timeout, max_bytes, *, _proxy=None):
    """GET one hop with TLS hostname verification and a pinned validated IP.

    A wall-clock watchdog interrupts slow headers and trickling response bodies.
    No urllib opener, .netrc, cookies, redirect handler or implicit proxy is used.
    The optional private proxy configuration comes only from the trusted broker.
    """
    parts = urlsplit(url)
    _url(url, provider=parts.hostname in SEARCH_HOSTS)
    addresses = _addresses(addresses)
    connection = _PinnedHTTPS(parts.hostname, addresses[0], timeout, proxy=_proxy, max_bytes=max_bytes)
    connection.response_class = lambda *args, **kwargs: _LimitedResponse(
        *args, max_bytes=max_bytes - connection.connect_bytes, **kwargs,
    )
    deadline = time.monotonic() + timeout
    watchdog = threading.Timer(timeout, connection.abort)
    watchdog.daemon = True
    watchdog.start()
    try:
        connection.connect()
        connection.request("GET", urlunsplit(("", "", parts.path or "/", parts.query, "")), headers={
            "Host": parts.hostname,
            "User-Agent": "PublicKnowledgeBroker/1.0",
            "Accept": "text/html, text/plain, application/rss+xml, application/xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        response = connection.getresponse()
        headers = {}
        for name, value in response.getheaders():
            name = name.lower()
            if name in {"content-type", "content-encoding", "content-length", "location"}:
                if name in headers:
                    raise _Unavailable("duplicate_response_header")
                headers[name] = value
        chunks = []
        header_bytes = (response.header_bytes if isinstance(response.header_bytes, int) else 0) + connection.connect_bytes
        remaining = max_bytes - header_bytes
        wire_limited = False
        while remaining:
            available_time = deadline - time.monotonic()
            if available_time <= 0:
                raise _Unavailable("network_timeout")
            connection.tls_socket.settimeout(available_time)
            try:
                chunk = response.read1(min(16384, remaining))
            except _RawLimit:
                wire_limited = True
                break
            except http.client.IncompleteRead:
                if isinstance(response.raw_reader.used, int) and response.raw_reader.used + connection.connect_bytes >= max_bytes:
                    wire_limited = True
                    break
                raise
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        wire_bytes = response.raw_reader.used
        if not isinstance(wire_bytes, int):
            wire_bytes = header_bytes + len(body)
        else:
            wire_bytes += connection.connect_bytes
        return Response(response.status, headers, body,
                        truncated=remaining == 0 or wire_limited or wire_bytes == max_bytes,
                        header_bytes=header_bytes, wire_bytes=wire_bytes)
    finally:
        watchdog.cancel()
        connection.abort()
        connection.close()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _clip(text, limit=MAX_CONTENT_BYTES):
    encoded = text.encode("utf-8")
    return encoded[:limit].decode("utf-8", errors="ignore"), len(encoded) > limit


def _text(body, content_type):
    decoded = body.decode("utf-8", errors="replace")
    if content_type == "text/html":
        parser = _Text()
        parser.feed(decoded)
        decoded = " ".join(" ".join(parser.parts).split())
    return decoded


class PublicKnowledge:
    """Per-call broker client with private, exclusive raw JSON receipt files.

    Results always contain status, URL, UTC retrieval timestamp, content SHA-256,
    truncation/unavailability reason, untrusted_data and receipt_path. Search also
    returns at most eight allowlisted result URLs and bounded titles/snippets.
    SHA-256 covers returned UTF-8 content; raw bodies have separate receipt SHAs.
    Invalid inputs are redacted rather than persisted. Network errors never echo
    exception strings, response authentication headers or cookies into receipts.
    """

    def __init__(self, *, record, transport=None, resolver=None, timeout=10.0):
        if not isinstance(timeout, (float, int)) or not 0 < timeout <= 30:
            raise ValueError("timeout must be within (0, 30] seconds")
        self.record = Path(record)
        self.transport = transport or https_get
        self.resolver = resolver or resolve_public
        self.timeout = timeout

    def _fetch(self, url, provider, responses, deadline):
        remaining_bytes = MAX_RAW_BYTES
        for hop in range(MAX_REDIRECTS + 1):
            url = _url(url, provider=provider)
            host = urlsplit(url).hostname
            remaining_time = deadline - time.monotonic()
            addresses = _addresses(_bounded(lambda: self.resolver(host, remaining_time), remaining_time))
            remaining_time = deadline - time.monotonic()
            response = _bounded(
                lambda: self.transport(url, addresses, remaining_time, remaining_bytes), remaining_time,
            )
            if (not isinstance(response, Response) or not isinstance(response.body, bytes)
                    or not isinstance(response.header_bytes, int) or response.header_bytes < 0
                    or response.header_bytes > remaining_bytes
                    or not isinstance(response.wire_bytes, int) or not 0 <= response.wire_bytes <= remaining_bytes):
                raise _Unavailable("invalid_transport_response")
            body_budget = remaining_bytes - response.header_bytes
            body = response.body[:body_budget]
            truncated = response.truncated or len(response.body) >= body_budget
            wire_bytes = max(response.wire_bytes, response.header_bytes + len(body))
            remaining_bytes -= wire_bytes
            headers = {name.lower(): value for name, value in response.headers.items()}
            recorded_headers = {name: value for name, value in headers.items()
                                if name in {"content-type", "content-encoding", "content-length"}}
            if "location" in headers:
                try:
                    recorded_headers["location"] = _url(urljoin(url, headers["location"]), provider=provider)
                except (ValueError, TypeError, _Unavailable):
                    recorded_headers["location"] = None
            responses.append({
                "url": url, "retrieved_at": _now(), "status": response.status,
                "body_base64": base64.b64encode(body).decode("ascii"),
                "sha256": hashlib.sha256(body).hexdigest(), "truncated": truncated,
                "header_bytes": response.header_bytes,
                "wire_bytes": wire_bytes, "headers": recorded_headers,
            })
            if response.status in {301, 302, 303, 307, 308}:
                if hop == MAX_REDIRECTS or not remaining_bytes:
                    raise _Unavailable("redirect_or_raw_limit")
                location = headers.get("location")
                if not isinstance(location, str) or not location:
                    raise _Unavailable("redirect_missing_location")
                _decoded(location)
                if location != location.strip() or any(ord(character) < 32 for character in location):
                    raise _Unavailable("unsafe_redirect")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise _Unavailable("http_status_" + str(response.status))
            if headers.get("content-encoding", "identity").lower() != "identity":
                raise _Unavailable("compressed_response_not_supported")
            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in _TEXT_TYPES:
                raise _Unavailable("unsupported_content_type")
            return url, body, content_type, truncated
        raise _Unavailable("redirect_limit")

    def _call(self, operation, value):
        result = {
            "status": "unavailable", "url": None, "retrieved_at": _now(),
            "content": "", "content_sha256": hashlib.sha256(b"").hexdigest(),
            "truncated": False, "reason": None, "untrusted_data": True,
        }
        if operation == "search_public":
            result["results"] = []
        responses = []
        accepted_input = None
        try:
            if operation not in {"search_public", "read_public"}:
                raise _Unavailable("invalid_action")
            if operation == "search_public":
                accepted_input = _query(value)
                url = SEARCH_URL + "?" + urlencode({"format": "rss", "q": accepted_input})
            else:
                url = _url(value)
                accepted_input = url
            result["url"] = url
            url, body, content_type, raw_truncated = self._fetch(
                url, operation == "search_public", responses, time.monotonic() + self.timeout,
            )
            result["url"] = url
            if operation == "search_public":
                content = self._search_results(body, result)
            else:
                content = _text(body, content_type)
            content, content_truncated = _clip(content)
            result.update(
                status="ok", content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                truncated=raw_truncated or content_truncated or result["truncated"],
                reason="raw_response_limit" if raw_truncated else (
                    "content_limit" if content_truncated else result["reason"]
                ),
            )
        except _Unavailable as failure:
            result["reason"] = str(failure)
        except Exception:
            result["reason"] = "network_or_parse_unavailable"
        if responses:
            result["retrieved_at"] = responses[-1]["retrieved_at"]
            if any(response["truncated"] for response in responses):
                result["truncated"] = True
        self.record.mkdir(parents=True, exist_ok=True)
        receipt_path = self.record / ("knowledge-" + uuid.uuid4().hex + ".json")
        result["receipt_path"] = str(receipt_path.absolute())
        receipt = {
            "operation": operation, "input": accepted_input,
            "untrusted_data": True, "responses": responses, "result": result,
        }
        descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(receipt, output, ensure_ascii=True, sort_keys=True)
            output.write("\n")
        return result

    @staticmethod
    def _search_results(body, result):
        if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", body, re.IGNORECASE):
            raise _Unavailable("unsafe_search_xml")
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            raise _Unavailable("invalid_search_response") from None
        found = []
        seen = set()
        for item in root.iter("item"):
            try:
                url = _url(item.findtext("link", ""))
            except _Unavailable:
                continue
            title = _text(item.findtext("title", "").encode(), "text/html")
            snippet = _text(item.findtext("description", "").encode(), "text/html")
            if _sensitive(title) or _sensitive(snippet) or url in seen:
                continue
            title, unused = _clip(title, 512)
            snippet, unused = _clip(snippet, 1536)
            candidate = {"url": url, "title": title, "snippet": snippet}
            if len(json.dumps(found + [candidate], ensure_ascii=False, sort_keys=True).encode()) > MAX_CONTENT_BYTES:
                result.update(truncated=True, reason="search_results_limit")
                break
            found.append(candidate)
            seen.add(url)
            if len(found) == MAX_RESULTS:
                result.update(truncated=True, reason="search_results_limit")
                break
        if not found:
            raise _Unavailable("no_allowed_public_results")
        result["results"] = found
        return json.dumps(found, ensure_ascii=False, sort_keys=True)

    def search_public(self, query):
        return self._call("search_public", query)

    def read_public(self, url):
        return self._call("read_public", url)


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def search_public(query, *, record, transport=None, resolver=None, timeout=10.0):
    return PublicKnowledge(record=record, transport=transport, resolver=resolver, timeout=timeout).search_public(query)


def read_public(url, *, record, transport=None, resolver=None, timeout=10.0):
    return PublicKnowledge(record=record, transport=transport, resolver=resolver, timeout=timeout).read_public(url)


def dispatch_public(action, record, *, transport=None, resolver=None, timeout=10.0):
    """Strict broker action, returning completed/unavailable and a raw receipt.

    Only the trusted caller may supply record or the keyword-only test hooks.
    Extra action fields (including headers, environment or transport) fail closed.
    The persisted low-level receipt uses ok for successful retrieval; this adapter
    normalizes only its returned status to completed for broker dispatch.
    """
    client = PublicKnowledge(record=record, transport=transport, resolver=resolver, timeout=timeout)
    if isinstance(action, dict) and action.get("kind") == "search_public" and set(action) == {"kind", "query"}:
        result = client.search_public(action["query"])
    elif isinstance(action, dict) and action.get("kind") == "read_public" and set(action) == {"kind", "url"}:
        result = client.read_public(action["url"])
    else:
        result = client._call("invalid_action", None)
    return dict(result, status="completed" if result["status"] == "ok" else "unavailable")


def _audit_require(condition):
    if not condition:
        raise _Unavailable("receipt_consistency_mismatch")


def _audit_receipt(receipt):
    operation = receipt["operation"]
    result = receipt["result"]
    responses = receipt["responses"]
    accepted_input = receipt["input"]
    provider = operation == "search_public"
    _audit_require(operation in {"search_public", "read_public", "invalid_action"})
    _audit_require(receipt["untrusted_data"] is True and result["untrusted_data"] is True)
    _audit_require(result["status"] in {"ok", "unavailable"} and len(responses) <= MAX_REDIRECTS + 1)
    _audit_require(datetime.fromisoformat(result["retrieved_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0)
    _audit_require(len(result["content"].encode()) <= MAX_CONTENT_BYTES)
    _audit_require(hashlib.sha256(result["content"].encode()).hexdigest() == result["content_sha256"])
    if accepted_input is None:
        _audit_require(not responses and result["status"] == "unavailable" and result["url"] is None)
        expected_url = None
    elif provider:
        _audit_require(_query(accepted_input) == accepted_input)
        expected_url = SEARCH_URL + "?" + urlencode({"format": "rss", "q": accepted_input})
    else:
        _audit_require(operation == "read_public")
        expected_url = _url(accepted_input)
    initial_url = expected_url
    total = 0
    last_body = b""
    for index, response in enumerate(responses):
        url = _url(response["url"], provider=provider)
        _audit_require(url == expected_url)
        body = base64.b64decode(response["body_base64"], validate=True)
        _audit_require(hashlib.sha256(body).hexdigest() == response["sha256"])
        header_bytes = response["header_bytes"]
        wire_bytes = response["wire_bytes"]
        _audit_require(isinstance(header_bytes, int) and header_bytes >= 0)
        _audit_require(isinstance(wire_bytes, int) and wire_bytes >= len(body) + header_bytes)
        total += wire_bytes
        _audit_require(total <= MAX_RAW_BYTES)
        headers = response["headers"]
        _audit_require(set(headers) <= {"content-type", "content-encoding", "content-length", "location"})
        if index + 1 < len(responses):
            _audit_require(response["status"] in {301, 302, 303, 307, 308})
            expected_url = _url(headers["location"], provider=provider)
        last_body = body
    if responses:
        _audit_require(result["retrieved_at"] == responses[-1]["retrieved_at"])
    if result["status"] == "ok":
        _audit_require(bool(responses) and responses[-1]["status"] == 200)
        _audit_require(result["url"] == responses[-1]["url"])
        headers = responses[-1]["headers"]
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        _audit_require(content_type in _TEXT_TYPES and headers.get("content-encoding", "identity").lower() == "identity")
        rebuilt = {"truncated": False, "reason": None}
        if provider:
            content = PublicKnowledge._search_results(last_body, rebuilt)
            _audit_require(rebuilt["results"] == result["results"])
        else:
            content = _text(last_body, content_type)
        content, clipped = _clip(content)
        raw_clipped = responses[-1]["truncated"]
        reason = "raw_response_limit" if raw_clipped else ("content_limit" if clipped else rebuilt["reason"])
        _audit_require(result["content"] == content and result["reason"] == reason)
        _audit_require(result["truncated"] == bool(raw_clipped or clipped or rebuilt["truncated"]))
    else:
        _audit_require(result["content"] == "" and bool(result["reason"]))
        _audit_require(result["url"] == initial_url or result["url"] in {response["url"] for response in responses})
        if provider:
            _audit_require(result["results"] == [])
    return {
        "valid": True, "status": "completed" if result["status"] == "ok" else "unavailable",
        "url": result["url"], "retrieved_at": result["retrieved_at"],
        "content_sha256": result["content_sha256"], "raw_response_count": len(responses),
        "wire_bytes": total,
    }


def audit_record(record):
    """Read-only offline consistency audit of one receipt or a call directory.

    Never follows receipt symlinks or embedded receipt_path values, never fetches
    URLs, and never executes stored text. Reads at most 64 receipts of 2 MiB each.
    Hash consistency is not proof of server identity or authenticated provenance.
    """
    audited = []
    try:
        path = Path(record)
        _audit_require(not path.is_symlink())
        paths = []
        if path.is_dir():
            for candidate in path.glob("knowledge-*.json"):
                paths.append(candidate)
                _audit_require(len(paths) <= 64)
            paths.sort()
        else:
            paths = [path]
        _audit_require(bool(paths))
        for receipt_path in paths:
            _audit_require(receipt_path.name.startswith("knowledge-") and receipt_path.suffix == ".json")
            descriptor = os.open(receipt_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                details = os.fstat(source.fileno())
                _audit_require(stat.S_ISREG(details.st_mode) and details.st_size <= 2 * MAX_RAW_BYTES)
                raw = source.read(2 * MAX_RAW_BYTES + 1)
                _audit_require(len(raw) <= 2 * MAX_RAW_BYTES)
            summary = _audit_receipt(json.loads(raw))
            audited.append(dict(summary, receipt_path=str(receipt_path.absolute())))
        return {"status": "completed", "valid": True, "reason": None, "receipts": audited}
    except Exception:
        return {"status": "unavailable", "valid": False, "reason": "invalid_or_unreadable_record", "receipts": audited}
