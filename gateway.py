from fastapi import FastAPI, Request
from fastapi.responses import Response
import uvicorn
import re
import logging
import httpx
import os
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

# --- LOGGING ENGINE ---
LOG_FILE = "sentinel.log"

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
    # 1. Check provider is valid
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
    headers.pop("content-length", None)  # ADD THIS LINE
    real_key = get_real_api_key(provider)
    if real_key:
        if provider == "anthropic":
            headers["x-api-key"] = real_key
        elif provider == "openai":
            headers["authorization"] = f"Bearer {real_key}"
        elif provider == "groq":
            headers["authorization"] = f"Bearer {real_key}"

    # 6. Forward to real API and return response
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method=request.method,
            url=real_url,
            headers=headers,
            content=scrubbed_body
        )

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