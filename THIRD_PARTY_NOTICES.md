# Third Party Notices

This project currently has no root project `LICENSE` file in this phase. This notice
lists third-party components that are used by the local judge, Problem Studio, tests,
or release packaging so distribution reviewers can verify license obligations.

## Runtime Dependencies

| Component | Used for | Distributed in runtime package | License to verify |
| --- | --- | --- | --- |
| FastAPI | Local HTTP APIs for judge Web and Problem Studio | Yes, when packaged with the Python application or standalone build | Project license at https://github.com/fastapi/fastapi |
| python-multipart | Multipart upload handling for Web APIs | Yes, when packaged with the Python application or standalone build | Project license at https://github.com/Kludex/python-multipart |
| PyYAML | `cases.yml` parsing | Yes, when packaged with the Python application or standalone build | Project license at https://github.com/yaml/pyyaml |
| Uvicorn | Local ASGI server | Yes, when packaged with the Python application or standalone build | Project license at https://github.com/encode/uvicorn |

## Bundled Browser Assets

| Component | Used for | Distributed in runtime package | License to verify |
| --- | --- | --- | --- |
| CodeMirror 5 | Problem Studio source editor and Vim keymap support | Yes, under `problem_studio/web/static/vendor/codemirror/` | Project license at https://github.com/codemirror/codemirror5 |

## Development And Test Dependencies

| Component | Used for | Distributed in runtime package | License to verify |
| --- | --- | --- | --- |
| httpx | Test client dependency through FastAPI/Starlette tests | No, dev/test only | Project license at https://github.com/encode/httpx |
| Nuitka | Standalone executable build | No, build tool only | Project license at https://github.com/Nuitka/Nuitka |
| Playwright | Browser E2E tests | No, dev/test only | Project license at https://github.com/microsoft/playwright |
| Ruff | Lint and format checks | No, dev/test only | Project license at https://github.com/astral-sh/ruff |

## Templates And Generated Artifacts

| Component | Used for | Distributed in runtime package | License to verify |
| --- | --- | --- | --- |
| `testlib.h` | Problem generator, validator, checker, and answer helper templates | May be copied into source problem workspaces or source packages | Upstream notice should be verified before public redistribution |

## Release Policy Notes

- Standalone release archives should include this file as `THIRD_PARTY_NOTICES.md`.
- `scripts/scan_release_artifact.py` fails standalone archives that omit this file.
- `.aljpack` release assets should be published with a sidecar SHA-256 checksum file named `<asset>.sha256`.
- Public-key signing for `.aljpack` files is intentionally out of scope for this phase.
