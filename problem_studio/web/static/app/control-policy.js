/**
 * 화면 control의 활성 조건과 비활성 사유를 한 곳에서 계산합니다.
 */

import { state } from "./state.js";

const contextProviders = new WeakMap();
const dependentControls = new WeakMap();

function addDescription(element, id) {
  if (!id) return;
  const ids = new Set((element.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
  ids.add(id);
  element.setAttribute("aria-describedby", Array.from(ids).join(" "));
}

function updateReasonTarget(targetId) {
  if (!targetId) return;
  const target = document.getElementById(targetId);
  if (!target) return;
  const reasons = Array.from(document.querySelectorAll("[data-control-policy-reason-target]"))
    .filter((element) => element.dataset.controlPolicyReasonTarget === targetId)
    .map((element) => element.dataset.disabledReason || "")
    .filter((reason, index, values) => reason && values.indexOf(reason) === index);
  target.textContent = reasons.length
    ? reasons.join(" ")
    : "현재 Git 작업을 사용할 수 있습니다.";
}

function enabled() {
  return { disabled: false, reason: "" };
}

function disabled(reason) {
  return { disabled: true, reason };
}

function loadingState(model) {
  return Number(model.loadingDepth || 0) > 0
    ? disabled("다른 작업을 처리하는 동안에는 사용할 수 없습니다.")
    : enabled();
}

function gitControlState(policyKey, model) {
  const status = model.gitStatus;
  if (!status?.isRepository) return disabled("Git 저장소가 아닙니다.");
  if (!status.writeEnabled) {
    return disabled("서버 정책으로 Git 쓰기/네트워크 작업이 차단되었습니다.");
  }
  if (status.toolRepositoryRemote) {
    return disabled("문제 저장소가 아니라 도구 저장소 원격 주소라서 차단되었습니다.");
  }
  if (policyKey === "git.commit" && !(status.files?.length || 0)) {
    return disabled("커밋할 변경 파일이 없습니다.");
  }
  if (policyKey === "git.push" && Number(status.behind || 0) > 0) {
    return disabled("원격보다 뒤처져 있어 먼저 당겨오기가 필요합니다.");
  }
  return loadingState(model);
}

function buildControlState(policyKey, model) {
  const context = model.controlContext || {};
  if (policyKey === "build.bulk-start" && !context.selectedCount) {
    return disabled("팩에 포함할 문제를 하나 이상 선택하세요.");
  }
  if (policyKey === "build.bulk-all" && !context.hasProblems) {
    return disabled("등록된 문제가 없습니다.");
  }
  if (context.packActive) {
    return disabled(context.packReason || "팩 빌드가 진행 중입니다.");
  }
  if (context.bulkActive) {
    return disabled(context.bulkReason || "전체 문제 빌드가 진행 중입니다.");
  }
  if (context.packPrerequisiteMissing) {
    return disabled(
      context.packPrerequisiteReason || "전체 테스트를 통과한 뒤 팩을 빌드할 수 있습니다."
    );
  }
  if (context.runAllActive || context.lockedByAnotherTab) {
    return disabled(context.runAllReason || "전체 테스트가 진행 중입니다.");
  }
  return loadingState(model);
}

/**
 * control policy key와 현재 상태로 disabled 여부와 사용자 안내 사유를 계산합니다.
 */
export function deriveControlState(policyKey, model = state) {
  if (policyKey.startsWith("git.")) return gitControlState(policyKey, model);
  if (policyKey.startsWith("build.")) return buildControlState(policyKey, model);

  const context = model.controlContext || {};
  if (policyKey === "solution.cases" && !context.hasSolutionCheck) {
    return disabled("테스트 후 결과를 볼 수 있습니다.");
  }
  if (
    policyKey === "solution.delete"
    && context.isReferenceSolution
    && !context.hasReplacementSolution
  ) {
    return disabled("기준 정답을 삭제하려면 다른 Accepted 솔루션이 필요합니다.");
  }
  if (policyKey === "problem.delete") {
    if (!model.selectedProblem) return disabled("삭제할 문제를 먼저 선택하세요.");
    if (!context.deleteConfirmationMatches) {
      return disabled("삭제 확인 문구를 정확히 입력하세요.");
    }
  }
  if (policyKey === "tab.action" && !model.selectedProblem) {
    return disabled("작업할 문제를 먼저 선택하세요.");
  }
  return loadingState(model);
}

function restoreEnabledTitle(element) {
  const title = element.dataset.controlPolicyEnabledTitle || "";
  if (title) element.title = title;
  else element.removeAttribute("title");
}

function applyControlState(element, controlState) {
  element.disabled = controlState.disabled;
  element.toggleAttribute("disabled", controlState.disabled);
  if (controlState.disabled && controlState.reason) {
    element.title = controlState.reason;
    element.dataset.disabledReason = controlState.reason;
  } else {
    restoreEnabledTitle(element);
    delete element.dataset.disabledReason;
  }
  for (const dependent of dependentControls.get(element) || []) {
    dependent.disabled = controlState.disabled;
    dependent.toggleAttribute("disabled", controlState.disabled);
    if (controlState.disabled && controlState.reason) dependent.title = controlState.reason;
    else dependent.removeAttribute("title");
  }
  updateReasonTarget(element.dataset.controlPolicyReasonTarget || "");
}

/**
 * DOM control에 policy와 현재 문맥 공급자를 연결합니다.
 */
export function bindControlPolicy(element, policyKey, options = {}) {
  if (!element) return;
  element.dataset.controlPolicy = policyKey;
  if (Object.hasOwn(options, "enabledTitle")) {
    element.dataset.controlPolicyEnabledTitle = options.enabledTitle || "";
  } else if (!Object.hasOwn(element.dataset, "controlPolicyEnabledTitle")) {
    element.dataset.controlPolicyEnabledTitle = element.getAttribute("title") || "";
  }
  if (options.context) contextProviders.set(element, options.context);
  if (options.reasonTarget) {
    element.dataset.controlPolicyReasonTarget = options.reasonTarget;
    addDescription(element, options.reasonTarget);
  }
  if (options.dependents) {
    const dependents = Array.from(options.dependents).filter(Boolean);
    dependentControls.set(element, dependents);
    for (const dependent of dependents) addDescription(dependent, options.reasonTarget || "");
  }
  const context = contextProviders.get(element)?.() || {};
  applyControlState(element, deriveControlState(policyKey, {
    ...state,
    controlContext: context,
  }));
}

/**
 * 연결된 control 중 지정한 policy를 다시 계산합니다.
 */
export function renderControlPolicies(policyKeys = null) {
  const requested = policyKeys ? new Set(policyKeys) : null;
  for (const element of document.querySelectorAll("[data-control-policy]")) {
    const policyKey = element.dataset.controlPolicy;
    if (requested && !requested.has(policyKey)) continue;
    const context = contextProviders.get(element)?.() || {};
    applyControlState(element, deriveControlState(policyKey, {
      ...state,
      controlContext: context,
    }));
  }
}
