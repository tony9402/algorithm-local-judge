from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from problem_studio.core.bulk import build_all_problem_packs
from problem_studio.web.routes.common import stream_operation, workspace_from_request
from problem_studio.web.schemas import BulkPackBuildRequest

router = APIRouter(prefix="/api/workspace", tags=["workspace"])
PACK_OUTPUT_DIR = Path("dist/packs")


@router.post("/packs/build-all/stream")
def api_workspace_pack_build_all_stream(
    request: Request,
    body: BulkPackBuildRequest,
) -> StreamingResponse:
    """Full-test selected problems and build one pack containing them."""
    workspace = workspace_from_request(request)

    def operation(progress):
        progress("Starting full workspace test and pack build.")
        result = build_all_problem_packs(
            workspace,
            body.pack_id,
            PACK_OUTPUT_DIR,
            body.platform_id,
            body.verify_profile,
            body.force,
            progress,
            body.max_workers,
            body.problem_ids,
        )
        progress(result["summary"])
        return result

    return StreamingResponse(stream_operation(operation), media_type="text/event-stream")
