"""종단 간 테스트에서 여러 시나리오가 공유하는 경로와 실행 환경 보조 기능을 제공하는 모듈입니다."""

from __future__ import annotations

from tests.e2e.browser_helpers import (
    BrowserE2ETestCase,
    LocalServer,
    assert_no_overlap,
    assert_visible_in_viewport,
    free_port,
    run_app,
    wait_for_http,
    wait_for_text,
    wait_for_value,
)
from tests.e2e.judge_cli_helpers import (
    JUDGE_COMMAND,
    ROOT,
    assert_cli_failed,
    judge_env,
    run_dir_from_stdout,
    run_judge_cli,
    write_trivial_python_source,
)
from tests.e2e.pack_fixtures import (
    create_minimal_pack,
    create_runnable_minimal_pack,
    create_source_archive,
    create_source_package,
    create_unsafe_tar,
    create_unsafe_tar_link,
    create_unsafe_zip,
    create_unsafe_zip_symlink,
    sha256_bytes,
    sse_event,
    sse_stream,
)
from tests.e2e.runtime_helpers import isolated_runtime, temporary_env
from tests.e2e.studio_ui_helpers import (
    click_by_text,
    create_studio_problem,
    set_solution_modal_editor_value,
    set_studio_editor_value,
    studio_editor_value,
    wait_for_studio_file_ready,
)

__all__ = [
    "BrowserE2ETestCase",
    "JUDGE_COMMAND",
    "LocalServer",
    "ROOT",
    "assert_cli_failed",
    "assert_no_overlap",
    "assert_visible_in_viewport",
    "click_by_text",
    "create_minimal_pack",
    "create_runnable_minimal_pack",
    "create_source_archive",
    "create_source_package",
    "create_studio_problem",
    "create_unsafe_tar",
    "create_unsafe_tar_link",
    "create_unsafe_zip",
    "create_unsafe_zip_symlink",
    "free_port",
    "isolated_runtime",
    "judge_env",
    "run_app",
    "run_dir_from_stdout",
    "run_judge_cli",
    "set_solution_modal_editor_value",
    "set_studio_editor_value",
    "sha256_bytes",
    "sse_event",
    "sse_stream",
    "studio_editor_value",
    "temporary_env",
    "wait_for_http",
    "wait_for_studio_file_ready",
    "wait_for_text",
    "wait_for_value",
    "write_trivial_python_source",
]
