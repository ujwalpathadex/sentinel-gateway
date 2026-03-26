from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn
import re
import logging
import httpx
import os
import json
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# --- DLP ENGINE ---
SENSITIVE_PATTERNS = {
    "AWS_KEY": r"AKIA[0-9A-Z]{16}",
    "STRIPE_KEY": r"sk_live_[0-9a-zA-Z]{24}",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "GENERIC_SECRET": r"(?i)(password|passwd|secret|api_key)['\"]?\s*[:=]\s*['\"]?([a-zA-Z0-9]{12,})"
}

def scrub(text: str):
    found = []
    for label, pattern in SENSITIVE_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            found.append(label)
            text = re.sub(pattern, f"[REDACTED_{label}]", text)
    return text, found

# ── CHANGE 1: Structured log path (replaces plain text LOG_FILE) ────────────
SENTINEL_LOG = Path.home() / ".sentinel" / "sentinel.log"
SENTINEL_LOG.parent.mkdir(parents=True, exist_ok=True)

PRICING = {
    "claude-opus":   {"input": 15.00, "output": 75.00},
    "claude-sonnet": {"input":  3.00, "output": 15.00},
    "claude-haiku":  {"input":  0.25, "output":  1.25},
}

def log_request(model: str, prompt_text: str, input_tokens: int,
                output_tokens: int, leaks: list, blocked: bool):
    """Write one structured JSON line — dashboard reads this."""
    key = next((k for k in PRICING if k in model.lower()), "claude-sonnet")
    p   = PRICING[key]
    cost = (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000

    entry = {
        "type":           "request",
        "timestamp":      datetime.utcnow().isoformat(),
        "model":          model,
        "input_tokens":   input_tokens,
        "output_tokens":  output_tokens,
        "cost":           round(cost, 6),
        "secrets_found":  len(leaks),
        "secrets":        leaks,
        "blocked":        blocked,
        "prompt_preview": prompt_text[:120].replace("\n", " "),
    }
    with open(SENTINEL_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")
# ────────────────────────────────────────────────────────────────────────────

# --- LOGGING ENGINE (keep for terminal output) ---
LOG_FILE = str(Path.home() / ".sentinel" / "sentinel.log")

class ImmediateFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

file_handler = ImmediateFileHandler(LOG_FILE)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
)

logger = logging.getLogger("sentinel")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

# --- PROVIDER ROUTING ---
PROVIDERS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "groq": "https://api.groq.com/openai",
}

def get_real_api_key(provider: str):
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY")
    if provider == "groq":
        return os.getenv("GROQ_API_KEY")
    return None

# --- ENDPOINTS ---
@app.get("/health")
async def health():
    return {
        "status": "Sentinel is alive",
        "providers": list(PROVIDERS.keys())
    }

@app.post("/inspect")
async def inspect(request: Request):
    body = await request.body()
    text = body.decode("utf-8")
    scrubbed, leaks = scrub(text)
    if leaks:
        print(f"[SENTINEL BLOCKED] Found: {', '.join(leaks)}")
        logger.warning(f"[ALERT] Blocked {', '.join(leaks)} in POST request")
    else:
        print(f"[SENTINEL CLEAN] No secrets found")
    return {
        "status": "clean" if not leaks else "scrubbed",
        "leaks_found": leaks,
        "cleaned_body": scrubbed
    }

@app.api_route("/{provider}/{path:path}", methods=["GET", "POST"])
async def forward(provider: str, path: str, request: Request):
    if provider not in PROVIDERS:
        return {"error": f"Unknown provider: {provider}. Use: {list(PROVIDERS.keys())}"}
    
    # 2. Read and scrub the request body
    body = await request.body()
    text = body.decode("utf-8")
    scrubbed_text, leaks = scrub(text)
    scrubbed_body = scrubbed_text.encode("utf-8")
    
     # 3. Log any leaks found
    if leaks:
        print(f"[SENTINEL BLOCKED] Found: {', '.join(leaks)} → forwarding clean version")
        logger.warning(f"[ALERT] Blocked {', '.join(leaks)} forwarding to {provider}/{path}")
    else:
        print(f"[SENTINEL] Clean request → forwarding to {provider}/{path}")

    # 4. Build the real URL
    real_url = f"{PROVIDERS[provider]}/{path}"
 
    # 5. Forward headers — inject real API key
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    real_key = get_real_api_key(provider)
    if real_key:
        if provider == "anthropic":
            headers["x-api-key"] = real_key
        elif provider in ("openai", "groq"):
            headers["authorization"] = f"Bearer {real_key}"

     # 6. Forward to real API and return response
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method=request.method,
            url=real_url,
            headers=headers,
            content=scrubbed_body
        )

    # ── CHANGE 2: Parse model + tokens from request/response, then log ──────
    try:
        req_json  = json.loads(text)
        model     = req_json.get("model", "unknown")
        messages  = req_json.get("messages", [])
        prompt    = " ".join(
            m.get("content", "") for m in messages
            if isinstance(m.get("content"), str)
        )
        # Try to get real token counts from response
        resp_json    = json.loads(response.content)
        usage        = resp_json.get("usage", {})
        input_tokens  = usage.get("input_tokens",  len(prompt.split()))
        output_tokens = usage.get("output_tokens", 0)
    except Exception:
        model, prompt, input_tokens, output_tokens = "unknown", text[:120], 0, 0

    log_request(
        model=model,
        prompt_text=prompt,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        leaks=leaks,
        blocked=bool(leaks),
    )
    # ─────────────────────────────────────────────────────────────────────────

    logger.info(f"[FORWARD] {provider}/{path} → {response.status_code}")
    skip_headers = {"content-encoding", "transfer-encoding",
                    "content-length", "connection"}
    clean_headers = {
        k: v for k, v in response.headers.items()
        if k.lower() not in skip_headers
    }
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=clean_headers
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8080)
