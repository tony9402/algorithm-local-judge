export function streamProgressDetail(message) {
  const raw = String(message || "");
  const bare = raw.replace(/^[^:]+:\s*/, "");
  const toolNames = {
    generator: "Generator",
    validator: "Validator",
    checker: "Checker",
    solution: "기준 정답",
  };
  let match = bare.match(
    /^Compiling (generator|validator|checker|solution) tool(?: \((\d+)\/(\d+)\))?\.$/
  );
  if (match) {
    const label = toolNames[match[1]] || match[1];
    return match[2] ? `${label} 컴파일 중 · ${match[2]}/${match[3]}` : `${label} 컴파일 중`;
  }
  match = bare.match(/^Compiling cases\.yml for profile ([^.]+)\.$/);
  if (match) return `${match[1]} cases.yml 검사 중`;
  if (bare === "Compiling cases.yml for every profile.") return "전체 profile cases.yml 검사 중";
  match = bare.match(/^Generating and validating profile (.+) \((\d+)\/(\d+)\)\.$/);
  if (match) {
    return `${match[1]} profile 생성 및 검증 중 · ${match[2]}/${match[3]} profile`;
  }
  match = bare.match(/^(\d+)\/(\d+) data generated and validated\.$/);
  if (match) return `${match[1]}/${match[2]}개 데이터 생성 및 검증 중`;
  match = bare.match(/^Profile (.+) complete: (\d+)\/(\d+) data generated and validated\.$/);
  if (match) return `${match[2]}/${match[3]}개 데이터 생성 및 검증 완료`;
  match = bare.match(/^Validating generated case .+ \((\d+)\/(\d+)\)\.$/);
  if (match) return `${match[1]}/${match[2]}개 데이터 검증 중`;
  match = bare.match(/^Verifying solution .+ \((\d+)\/(\d+)\)\.$/);
  if (match) return `${match[1]}/${match[2]}개 솔루션 검증 중`;
  if (bare.startsWith("Preparing generator tools")) {
    return "generator, validator, checker와 기준 정답 컴파일 준비 중";
  }
  if (bare.startsWith("Generating input cases")) return "입력 데이터 생성 중";
  if (bare.startsWith("Writing expected answer")) return "기준 정답 출력 생성 중";
  if (bare.startsWith("Self-checking answer")) return "checker self-check 중";
  if (bare.startsWith("Using cached data")) return "캐시된 데이터 사용 중";
  if (bare.startsWith("Generated data at")) return "데이터 생성 및 검증 완료";
  if (bare.startsWith("Generating validation data")) return "검증용 데이터 생성 중";
  if (bare === "Starting full test.") return "전체 테스트 시작";
  match = bare.match(/^Running (\d+) problems with (\d+) worker\(s\)\.$/);
  if (match) return `${match[1]}개 문제를 ${match[2]}개 워커로 병렬 실행 중`;
  if (bare === "Checking cases.yml.") return "cases.yml 검사 중";
  if (bare === "Compiling tools.") return "도구 컴파일 중";
  if (bare === "Generating and validating all data.") return "모든 데이터 생성+검증 중";
  if (bare === "Verifying expected solution results.") return "솔루션 기대 결과 검증 중";
  if (bare.startsWith("Building pack ")) return bare.replace(/^Building pack /, "팩 빌드 중: ");
  if (bare.startsWith("Pack built:")) return bare.replace(/^Pack built:\s*/, "팩 생성 완료: ");
  if (bare.startsWith("Full test failed:")) {
    return bare.replace(/^Full test failed:\s*/, "전체 테스트 실패: ");
  }
  if (bare.startsWith("Failed:")) return bare.replace(/^Failed:\s*/, "실패: ");
  if (bare === "Solution expectation verification finished.") return "솔루션 기대 결과 검증 완료";
  if (bare === "Solution expectation verification finished with mismatches.") {
    return "솔루션 기대 결과에서 다른 항목을 발견했습니다.";
  }
  return raw || "작업을 진행 중입니다.";
}

export function parseSseBlock(block) {
  const lines = block.split("\n");
  let event = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  return { event, data: dataLines.length ? JSON.parse(dataLines.join("\n")) : {} };
}
