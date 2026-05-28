from __future__ import annotations

from tests.e2e.browser_helpers import Page, wait_for_text, wait_for_value


def wait_for_studio_file_ready(page: Page, path: str, timeout: int = 15_000) -> None:
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
    page.locator(selector).filter(has_text=text).first.click()


def create_studio_problem(
    page: Page,
    problem_id: str,
    title: str,
    folder: str = "E2E",
) -> None:
    page.locator("#newProblemButton").click()
    page.locator("#newProblemId").fill(problem_id)
    page.locator("#newProblemTitle").fill(title)
    page.locator("#newProblemFolder").fill(folder)
    page.locator("#createProblemButton").click()
    wait_for_text(page, "#problemTitle", title)
    wait_for_value(page, "#metadataTitle", title)


def studio_editor_value(page: Page) -> str:
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
