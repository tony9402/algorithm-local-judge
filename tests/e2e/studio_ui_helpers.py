"""문제 스튜디오 브라우저 테스트에서 파일 편집기와 모달 입력을 안정적으로 조작하는 보조 기능 모듈입니다."""

from __future__ import annotations

from tests.e2e.browser_helpers import Page, wait_for_text, wait_for_value


def wait_for_studio_file_ready(page: Page, path: str, timeout: int = 15_000) -> None:
    """브라우저 화면에서 스튜디오 파일 준비 조건이 만족될 때까지 기다려 비동기 렌더링 경합을 줄입니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        path (str): 테스트가 조작할 파일 또는 문제 스튜디오 내부 경로입니다.
        timeout (int): 조건이 만족될 때까지 기다릴 최대 시간입니다.
    """
    page.wait_for_function(
        """([path]) => {
            const title = document.querySelector("#fileTitle");
            const status = document.querySelector("#fileStatus");
            return Boolean(
                title?.textContent.includes(path)
                && status?.textContent.includes("저장됨")
            );
        }""",
        arg=[path],
        timeout=timeout,
    )


def click_by_text(page: Page, selector: str, text: str) -> None:
    """클릭 텍스트 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        selector (str): 브라우저에서 대상 요소를 찾기 위한 CSS 선택자입니다.
        text (str): 파일에 기록하거나 브라우저에서 기다릴 텍스트입니다.
    """
    page.locator(selector).filter(has_text=text).first.click()


def create_studio_problem(
    page: Page,
    problem_id: str,
    title: str,
    folder: str = "E2E",
) -> None:
    """스튜디오 문제 테스트에 필요한 파일 구조와 아카이브를 만들어 설치, 업로드, 보안 검증 경로를 재현합니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        problem_id (str): 테스트가 생성하거나 조회할 문제 식별자입니다.
        title (str): 작업 목록이나 문제 메타데이터에 표시할 제목입니다.
        folder (str): 폴더 값을 지정하는 인자입니다.
    """
    page.locator("#newProblemButton").click()
    page.locator("#newProblemId").fill(problem_id)
    page.locator("#newProblemTitle").fill(title)
    page.locator("#newProblemFolder").fill(folder)
    page.locator("#createProblemButton").click()
    wait_for_text(page, "#problemTitle", title)
    wait_for_value(page, "#metadataTitle", title)


def studio_editor_value(page: Page) -> str:
    """스튜디오 편집기 값 테스트 보조 로직을 분리해 같은 검증 조건을 여러 시나리오에서 일관되게 사용합니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.

    Returns:
        str: 현재 문제 스튜디오 편집기에 표시된 소스 문자열입니다.
    """
    page.wait_for_function(
        """() => {
            const wrapper = document.querySelector("#codeEditor .studio-codemirror");
            return !wrapper || Boolean(wrapper.CodeMirror);
        }"""
    )
    return str(
        page.evaluate(
            """() => {
                const wrapper = document.querySelector("#codeEditor .studio-codemirror");
                if (wrapper?.CodeMirror) return wrapper.CodeMirror.getValue();
                const editor = document.querySelector("#fileEditor");
                return editor?.value || "";
            }"""
        )
    )


def set_studio_editor_value(page: Page, value: str) -> None:
    """브라우저 편집기나 입력창의 스튜디오 편집기 값 상태를 테스트가 원하는 값으로 맞춥니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        value (str): 해시하거나 입력창에 설정하거나 비교할 값입니다.
    """
    page.wait_for_function(
        """() => {
            const wrapper = document.querySelector("#codeEditor .studio-codemirror");
            return !wrapper || Boolean(wrapper.CodeMirror);
        }"""
    )
    page.evaluate(
        """(value) => {
            const wrapper = document.querySelector("#codeEditor .studio-codemirror");
            if (wrapper?.CodeMirror) {
                wrapper.CodeMirror.setValue(value);
                return;
            }
            const editor = document.querySelector("#fileEditor");
            editor.value = value;
            editor.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        value,
    )


def set_solution_modal_editor_value(page: Page, key: str, value: str) -> None:
    """브라우저 편집기나 입력창의 솔루션 모달 편집기 값 상태를 테스트가 원하는 값으로 맞춥니다.

    Args:
        page (Page): 브라우저 상호작용을 수행할 Playwright 페이지입니다.
        key (str): 키 값을 지정하는 인자입니다.
        value (str): 해시하거나 입력창에 설정하거나 비교할 값입니다.
    """
    index = 0 if key == "create" else 1
    textarea_id = "solutionCreateSource" if key == "create" else "solutionEditSource"
    page.evaluate(
        """([index, textareaId, value]) => {
            const wrappers = document.querySelectorAll(".source-modal-codemirror");
            const wrapper = wrappers[index];
            if (wrapper?.CodeMirror) {
                wrapper.CodeMirror.setValue(value);
                return;
            }
            const textarea = document.querySelector(`#${textareaId}`);
            textarea.value = value;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
        }""",
        [index, textarea_id, value],
    )
