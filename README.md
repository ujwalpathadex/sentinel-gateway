# Sentinel Gateway

> Your AI tools are sending things you haven't seen. Sentinel watches every request before it leaves your machine.

## What it does

Sentinel sits between your AI tools (Cursor, Claude Code, any AI tool) and their providers (Anthropic, OpenAI, Groq). Every request passes through it before leaving your machine.

- Catches and redacts AWS keys, Stripe keys, SSNs, and secrets before transmission
- Logs every request permanently to `sentinel.log.`
- Works across ALL AI tools simultaneously — one install, complete coverage
- Runs entirely locally — nothing goes to any cloud

## Install
```bash
git clone https://github.com/ujwalpathadex/sentinel-gateway
cd sentinel-gateway
pip install fastapi uvicorn httpx python-dotenv
```

## Setup

Create a `.env` file in the root folder:
```
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
```

## Run
```bash
python gateway.py
```

Gateway runs on `http://localhost:8080`

## How it works

Instead of calling AI providers directly, route your requests through Sentinel:

- Anthropic: `http://localhost:8080/anthropic/v1/messages`
- OpenAI: `http://localhost:8080/openai/v1/chat/completions`
- Groq: `http://localhost:8080/groq/v1/chat/completions`

  ## Use with Cursor and Claude Code

**Claude Code** — set this environment variable once:

**Mac/Linux** — add to ~/.zshrc or ~/.bashrc:
```bash
export ANTHROPIC_BASE_URL=http://localhost:8080/anthropic
```

**Windows** — add to System Environment Variables:
```
ANTHROPIC_BASE_URL=http://localhost:8080/anthropic
```

Restart Claude Code after setting. All requests automatically pass through Sentinel.

**Cursor BYOK (Bring Your Own Key):**
```bash
export ANTHROPIC_BASE_URL=http://localhost:8080/anthropic
export OPENAI_BASE_URL=http://localhost:8080/openai
```

> ⚠️ **Cursor Auto Mode** routes through Cursor's own servers and is not currently intercepted. Support planned for future release.

## What it catches

- AWS Keys (`AKIA...`)
- Stripe live keys (`sk_live_...`)
- Social Security Numbers
- Passwords, secrets, API keys in code

## Check your audit log
```bash
cat sentinel.log
```

## Roadmap

- [x] DLP engine — catches and redacts secrets
- [x] Permanent audit log
- [x] Multi-provider support (Anthropic, OpenAI, Groq)
- [x] Works with Claude Code and Cursor BYOK
- [ ] Automatic interception for Cursor Auto Mode
- [ ] Live dashboard — see what your AI tools transmit in real time
- [ ] One-command install script
- [ ] Team mode — shared audit log for small teams

## Status

Early stage. Working and tested. Built to solve a real problem — most developers have zero visibility into what their AI tools actually transmit.

Currently supports manual API routing—point your API calls to localhost:8080 instead of calling providers directly. Automatic interception for Cursor and Claude Code without configuration changes is on the roadmap.

## License

Copyright (c) 2026 Ujwal Pathadex. All rights reserved. Source visible for evaluation only.
