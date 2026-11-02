"""Calls to the language model, with as little use as possible.

Providers:
  deepseek   (default) deepseek-flash without thinking, key in DEEPSEEK_API_KEY
             or OPENAI_API_KEY; waits for off-peak hours unless --allow-peak.
  openai     any OpenAI-compatible endpoint (--base-url), key in OPENAI_API_KEY.
  anthropic  Claude, key in ANTHROPIC_API_KEY.

Every request adds its token use to USAGE; log_usage() appends a summary to
api_usage.jsonl so the spending of all sessions stays visible.
"""
import datetime
import json
import os
import threading
import time
import urllib.error
import urllib.request

DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"
# USD per 1M tokens at peak (input cache miss, input cache hit, output); off-peak is half.
PRICES = {"deepseek-flash": (0.30, 0.006, 1.20), "deepseek-v4-pro": (1.32, 0.044, 3.96)}
# DeepSeek peak hours (UTC), Monday to Friday: 01:00-04:00 and 06:00-10:00.
PEAK_HOURS = ((1, 4), (6, 10))


def is_peak(now=None) -> bool:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.weekday() < 5 and any(a <= now.hour < b for a, b in PEAK_HOURS)


def minutes_to_off_peak(now=None) -> int:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    t = now
    while is_peak(t):
        t += datetime.timedelta(minutes=1)
    return int((t - now).total_seconds() // 60)


class Usage:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = self.prompt = self.cached = self.output = 0
        self.cost = 0.0

    def add(self, model: str, prompt: int, cached: int, output: int):
        miss, hit, out = PRICES.get(model, (0.0, 0.0, 0.0))
        factor = 1.0 if is_peak() else 0.5
        with self.lock:
            self.requests += 1
            self.prompt += prompt
            self.cached += cached
            self.output += output
            self.cost += factor * ((prompt - cached) * miss + cached * hit + output * out) / 1e6

    def summary(self) -> str:
        return ("%d requests, %d input tokens (%d from cache), %d output tokens, about $%.3f"
                % (self.requests, self.prompt, self.cached, self.output, self.cost))


USAGE = Usage()


class Truncated(Exception):
    """The answer hit the output limit; ask again with fewer texts."""


def resolve(args):
    """Fill in provider defaults on args (model, base_url, key)."""
    if args.provider == "deepseek":
        args.base_url = args.base_url or DEEPSEEK_URL
        args.model = args.model or DEEPSEEK_MODEL
        args.key = args.key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    elif args.provider == "openai":
        args.model = args.model or "gpt-4o"
        args.key = args.key or os.environ.get("OPENAI_API_KEY", "")
    else:
        args.model = args.model or "claude-sonnet-5-5"
        args.key = args.key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not args.key:
        raise SystemExit("no API key: set DEEPSEEK_API_KEY (or OPENAI_API_KEY / ANTHROPIC_API_KEY)")
    return args


def wait_off_peak(args):
    if args.provider != "deepseek" or getattr(args, "allow_peak", False):
        return
    while is_peak():
        print("\npeak hours at DeepSeek (twice the price): waiting %d min (or use --allow-peak)"
              % minutes_to_off_peak(), flush=True)
        time.sleep(min(600, 60 * max(1, minutes_to_off_peak())))


def call(args, system: str, user: str) -> str:
    """One request. Raises Truncated when the answer was cut off."""
    wait_off_peak(args)
    if args.provider == "anthropic":
        url = (args.base_url or "https://api.anthropic.com") + "/v1/messages"
        body = {"model": args.model, "max_tokens": 8000, "system": system,
                "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": args.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    else:
        base = args.base_url.rstrip("/")
        if base.endswith("/v1"):        # e.g. https://api.siliconflow.cn/v1
            base = base[:-3]
        url = base + "/v1/chat/completions"
        # The fixed system prompt comes first, so its tokens are served from the cache.
        body = {"model": args.model, "temperature": 0.3, "max_tokens": 8000,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if args.provider == "deepseek":
            body["thinking"] = {"type": "disabled"}     # no paid reasoning tokens
        headers = {"authorization": "Bearer " + args.key, "content-type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    if args.provider == "anthropic":
        u = data.get("usage", {})
        USAGE.add(args.model, u.get("input_tokens", 0), u.get("cache_read_input_tokens", 0),
                  u.get("output_tokens", 0))
        if data.get("stop_reason") == "max_tokens":
            raise Truncated()
        return "".join(part.get("text", "") for part in data["content"])
    u = data.get("usage", {})
    USAGE.add(args.model, u.get("prompt_tokens", 0), u.get("prompt_cache_hit_tokens", 0),
              u.get("completion_tokens", 0))
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise Truncated()
    return choice["message"]["content"]


def log_usage(path, command: str, args, texts_done: int):
    if not USAGE.requests:
        return
    entry = {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "cmd": command, "model": args.model, "requests": USAGE.requests, "texts": texts_done,
             "input": USAGE.prompt, "cached": USAGE.cached, "output": USAGE.output,
             "usd": round(USAGE.cost, 4)}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def is_fatal(e: Exception) -> bool:
    return isinstance(e, urllib.error.HTTPError) and e.code in (400, 401, 402, 403, 404)
