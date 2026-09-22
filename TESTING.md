# Alpha Experience — verification
Date: 2026-09-22. Based on upstream commit 2e2446d7242336016dae838649b80a4847aa176e.

## Results

- Untouched upstream baseline: 57 pytest tests passed.
- Final Python suite: 75 passed (57 original + 18 new dashboard/API tests).
- Frontend pure-state suite: 26 passed.
- JavaScript syntax checks: passed.
- Wheel packaging: built successfully; dashboard.html, advanced.html, CSS, both JavaScript files, all 9 SVG icons and their MIT LICENSE included.
- Browser checks and visual fidelity: passed; see design-qa.md.
- git diff --check: passed (Git may report informational CRLF normalization warnings on Windows).

The first remote CI run exposed a pre-existing test portability issue: a
`*.txt` glob was expected to match `second.TXT` on Linux as it does on Windows.
The fixture now uses explicit case alternatives (`*.[tT][xX][tT]`) to test the
same two files on every platform. Production file-selection behavior is unchanged.

## Re-run

Install the project with its development dependencies in your selected environment:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
node --test tests/dashboard-state.test.cjs
node --check src/neuradock_agent/web/assets/dashboard.js
python -m pip wheel . --no-deps --no-build-isolation --no-cache-dir --wheel-dir artifacts/dist
```

Node is needed only for the dependency-free frontend state tests, not for running the Python Agent.

Local validation used isolated test dependencies. No remote LLM or real device was contacted. GitHub Actions runs the Python suite on Windows, macOS, and Linux with Python 3.9, 3.11, and 3.13, plus the frontend tests and syntax checks in a separate Node.js 22 job. Local pass counts above do not imply that a particular remote CI run has passed; check the pull request's checks for that result.

## Coverage

New tests cover ratio derivation, baseline warmup, invalid/zero Alpha, quality warnings, immediate device disconnect, stale inputs, declared source kind vs filename guesses, invalid manual input, reset/source boundaries, asset traversal/MIME, and existing API behavior. Frontend tests cover conservative unknown/null/nonfinite data handling, source labels, pause and stale/disconnected feedback, historical gaps, 60-second windows, safe IPv4/hostname command generation and shell-injection rejection.

The browser checks exercise actual DOM/UI behavior. They are documented in design-qa.md rather than supplied as an independent Playwright dependency. Live-device performance and real-subject outcomes remain unverified.

## Preview

```powershell
python -m neuradock_agent serve --host 127.0.0.1 --port 8875
```

Open http://127.0.0.1:8875/ . This defaults to SYNTHETIC DEMO, not live EEG. Stop with Ctrl+C. For an actual device, use the confirmed host/port described in docs/alpha-experience.md.
