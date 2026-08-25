"""Signed Docker launcher의 exact command와 fail-closed 계약 테스트입니다."""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alj_core.config import effective_tool_compile_timeout_ms
from judge.cli import main
from judge.cli_parser import build_parser
from judge.core.docker_launcher import (
    COSIGN_VERIFIER_IMAGE,
    DATA_VOLUME,
    INTERNAL_NETWORK,
    ISOLATED_GATEWAY_OPTION,
    JUDGE_DOCKER_WEB,
    MANAGED_LABEL,
    MANAGED_LABEL_KEY,
    OFFICIAL_IMAGE,
    OFFICIAL_IMAGE_IDENTITY,
    OFFICIAL_IMAGE_REPOSITORY,
    OFFICIAL_PROBLEM_REPOSITORY,
    PORT_LABEL_KEY,
    SERVICE_LABEL_KEY,
    SETUP_MARKER,
    WORKSPACE_LABEL_KEY,
    docker_web_status,
    restart_docker_web,
    run_docker_web,
    setup_docker_judge,
    start_docker_studio_web,
    start_docker_web,
    stop_docker_web,
)
from judge.core.errors import JudgeError
from judge.core.pack_signatures import DEFAULT_GITHUB_OIDC_ISSUER
from judge.core.remote_install import download_problem_pack_from_github

ROOT = Path(__file__).resolve().parents[1]
DIGEST = f"{OFFICIAL_IMAGE_REPOSITORY}@sha256:{'a' * 64}"
PRECHECK = ("docker", {"serverVersion": "28.0.0"})


def completed(
    returncode: int = 0,
    *,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


def signature_command() -> list[str]:
    return [
        "/usr/bin/cosign",
        "verify",
        DIGEST,
        "--certificate-identity",
        OFFICIAL_IMAGE_IDENTITY,
        "--certificate-oidc-issuer",
        DEFAULT_GITHUB_OIDC_ISSUER,
    ]


def containerized_signature_command() -> list[str]:
    return ["docker", "run", "--rm", COSIGN_VERIFIER_IMAGE, *signature_command()[1:]]


def setup_container_command() -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        "algorithm-local-judge-setup",
        "--network",
        "bridge",
        "--user",
        "10001:10001",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--tmpfs",
        "/home/alj/.sigstore:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        "256",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--cpus",
        "2.0",
        "--mount",
        f"type=volume,source={DATA_VOLUME},target=/data",
        DIGEST,
        "/bin/sh",
        "-c",
        f"mkdir -p /data/jobs && rm -f {SETUP_MARKER} "
        f'&& judge problem install "$1" --require-pack '
        f"&& touch {SETUP_MARKER}",
        "alj-docker-setup",
        OFFICIAL_PROBLEM_REPOSITORY,
    ]


def web_container_command(port: int) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        "algorithm-local-judge-web",
        "--label",
        MANAGED_LABEL,
        "--label",
        f"{SERVICE_LABEL_KEY}=judge-web",
        "--label",
        f"{PORT_LABEL_KEY}={port}",
        "--network",
        INTERNAL_NETWORK,
        "--user",
        "10001:10001",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=256m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        "256",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--cpus",
        "2.0",
        "--tmpfs",
        "/workspace:rw,noexec,nosuid,nodev,size=512m,uid=10001,gid=10001,mode=0700",
        "--mount",
        f"type=volume,source={DATA_VOLUME},target=/data,readonly",
        "--tmpfs",
        "/data/cache:rw,nosuid,nodev,size=1024m,uid=10001,gid=10001,mode=0700",
        "--tmpfs",
        "/data/jobs:rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001,mode=0700",
        "--publish",
        f"0.0.0.0:{port}:{port}",
        DIGEST,
        "judge",
        "web",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--no-open",
        "--allow-remote-run",
    ]


def setup_marker_command() -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "10001:10001",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--pids-limit",
        "16",
        "--memory",
        "128m",
        "--cpus",
        "0.5",
        "--mount",
        f"type=volume,source={DATA_VOLUME},target=/data,readonly",
        DIGEST,
        "/usr/bin/test",
        "-f",
        SETUP_MARKER,
    ]


class DockerLauncherCommandTest(unittest.TestCase):
    def test_setup_exactly_pulls_verifies_and_installs_into_volume(self) -> None:
        results = [
            completed(),
            completed(stdout=f"{DIGEST}\n"),
            completed(),
            completed(stdout=f"{DATA_VOLUME}\n"),
            completed(stdout="true\n"),
            completed(),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path", return_value="/usr/bin/cosign"),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
        ):
            resolved = setup_docker_judge()

        self.assertEqual(resolved, DIGEST)
        commands = [item.args[0] for item in run.call_args_list]
        self.assertEqual(
            commands,
            [
                ["docker", "pull", OFFICIAL_IMAGE],
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{index .RepoDigests 0}}",
                    OFFICIAL_IMAGE,
                ],
                signature_command(),
                ["docker", "volume", "create", "--label", MANAGED_LABEL, DATA_VOLUME],
                [
                    "docker",
                    "volume",
                    "inspect",
                    "--format",
                    f'{{{{index .Labels "{MANAGED_LABEL_KEY}"}}}}',
                    DATA_VOLUME,
                ],
                setup_container_command(),
            ],
        )
        self.assertFalse(run.call_args_list[-1].kwargs["capture_output"])

    def test_setup_rejects_mutable_or_invalid_image_reference_before_execution(self) -> None:
        results = [completed(), completed(stdout=f"{OFFICIAL_IMAGE}\n")]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path") as cosign,
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
            self.assertRaisesRegex(JudgeError, "pinned RepoDigest"),
        ):
            setup_docker_judge()

        self.assertEqual(run.call_count, 2)
        cosign.assert_not_called()

    def test_setup_uses_pinned_cosign_image_when_host_cosign_is_missing(self) -> None:
        results = [
            completed(),
            completed(stdout=f"{DIGEST}\n"),
            completed(),
            completed(stdout=f"{DATA_VOLUME}\n"),
            completed(stdout="true\n"),
            completed(),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch(
                "judge.core.docker_launcher.cosign_path",
                side_effect=JudgeError("Cosign is not installed"),
            ),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
        ):
            resolved = setup_docker_judge()

        self.assertEqual(resolved, DIGEST)
        commands = [item.args[0] for item in run.call_args_list]
        self.assertEqual(commands[2], containerized_signature_command())
        self.assertIn("@sha256:", COSIGN_VERIFIER_IMAGE)

    def test_setup_does_not_fallback_when_docker_preflight_fails(self) -> None:
        with (
            patch(
                "judge.core.docker_launcher.ensure_sandbox_preflight",
                side_effect=JudgeError("Docker unavailable"),
            ),
            patch("judge.core.docker_launcher.subprocess.run") as run,
            self.assertRaisesRegex(JudgeError, "Docker unavailable"),
        ):
            setup_docker_judge()

        run.assert_not_called()

    def test_launcher_requires_docker_engine_28_before_mutating_state(self) -> None:
        with (
            patch(
                "judge.core.docker_launcher.ensure_sandbox_preflight",
                return_value=("docker", {"serverVersion": "27.5.1"}),
            ),
            patch("judge.core.docker_launcher.subprocess.run") as run,
            self.assertRaisesRegex(JudgeError, r"Docker Engine 28\+"),
        ):
            setup_docker_judge()

        run.assert_not_called()

    def test_setup_pack_policy_rejects_source_archive_fallback(self) -> None:
        with (
            patch(
                "judge.core.remote_install.ensure_trusted_repository",
                return_value=OFFICIAL_PROBLEM_REPOSITORY,
            ),
            patch(
                "judge.core.remote_install.github_json",
                side_effect=JudgeError("release not found"),
            ),
            patch("judge.core.remote_install.github_default_branch") as default_branch,
            self.assertRaisesRegex(JudgeError, "signed release problem pack is required"),
        ):
            download_problem_pack_from_github(
                OFFICIAL_PROBLEM_REPOSITORY,
                require_pack=True,
            )

        default_branch.assert_not_called()

    def test_web_uses_internal_hardened_container_and_publishes_requested_port(self) -> None:
        results = [
            completed(returncode=1, stderr="No such object"),
            completed(stdout=f"{DIGEST}\n"),
            completed(),
            completed(stdout="true\n"),
            completed(),
            completed(returncode=1, stderr="network not found"),
            completed(stdout=f"{INTERNAL_NETWORK}\n"),
            completed(),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path", return_value="/usr/bin/cosign"),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
        ):
            run_docker_web(9876)

        commands = [item.args[0] for item in run.call_args_list]
        self.assertEqual(
            commands,
            [
                ["docker", "container", "inspect", "algorithm-local-judge-web"],
                [
                    "docker",
                    "image",
                    "inspect",
                    "--format",
                    "{{index .RepoDigests 0}}",
                    OFFICIAL_IMAGE,
                ],
                signature_command(),
                [
                    "docker",
                    "volume",
                    "inspect",
                    "--format",
                    f'{{{{index .Labels "{MANAGED_LABEL_KEY}"}}}}',
                    DATA_VOLUME,
                ],
                setup_marker_command(),
                [
                    "docker",
                    "network",
                    "inspect",
                    "--format",
                    f"{{{{.Internal}}}} {{{{.Driver}}}} "
                    f'{{{{index .Labels "{MANAGED_LABEL_KEY}"}}}} '
                    '{{index .Options "com.docker.network.bridge.gateway_mode_ipv4"}}',
                    INTERNAL_NETWORK,
                ],
                [
                    "docker",
                    "network",
                    "create",
                    "--driver",
                    "bridge",
                    "--internal",
                    "--opt",
                    ISOLATED_GATEWAY_OPTION,
                    "--label",
                    MANAGED_LABEL,
                    INTERNAL_NETWORK,
                ],
                web_container_command(9876),
            ],
        )
        self.assertFalse(run.call_args_list[-1].kwargs["capture_output"])
        self.assertIsNone(run.call_args_list[-1].kwargs["timeout"])

    def test_web_refuses_existing_non_internal_network(self) -> None:
        results = [
            completed(returncode=1, stderr="No such object"),
            completed(stdout=f"{DIGEST}\n"),
            completed(),
            completed(stdout="true\n"),
            completed(),
            completed(stdout="false bridge true isolated\n"),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path", return_value="/usr/bin/cosign"),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
            self.assertRaisesRegex(JudgeError, "expected a managed internal bridge network"),
        ):
            run_docker_web()

        self.assertEqual(run.call_count, 6)

    def test_web_stops_before_volume_or_network_when_signature_is_invalid(self) -> None:
        results = [
            completed(returncode=1, stderr="No such object"),
            completed(stdout=f"{DIGEST}\n"),
            completed(returncode=1, stderr="no matching signatures"),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path", return_value="/usr/bin/cosign"),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
            self.assertRaisesRegex(JudgeError, "signature verification failed"),
        ):
            run_docker_web()

        self.assertEqual(run.call_count, 3)

    def test_web_does_not_fallback_when_data_volume_is_missing(self) -> None:
        results = [
            completed(returncode=1, stderr="No such object"),
            completed(stdout=f"{DIGEST}\n"),
            completed(),
            completed(returncode=1, stderr="volume not found"),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path", return_value="/usr/bin/cosign"),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
            self.assertRaisesRegex(JudgeError, "judge docker setup"),
        ):
            run_docker_web()

        self.assertEqual(run.call_count, 4)

    def test_web_rejects_incomplete_setup_marker(self) -> None:
        results = [
            completed(returncode=1, stderr="No such object"),
            completed(stdout=f"{DIGEST}\n"),
            completed(),
            completed(stdout="true\n"),
            completed(returncode=1, stderr="marker missing"),
        ]
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight", return_value=PRECHECK),
            patch("judge.core.docker_launcher.cosign_path", return_value="/usr/bin/cosign"),
            patch("judge.core.docker_launcher.subprocess.run", side_effect=results) as run,
            self.assertRaisesRegex(JudgeError, "setup completion check failed"),
        ):
            run_docker_web()

        self.assertEqual(run.call_count, 5)

    def test_web_rejects_invalid_host_port_before_docker_access(self) -> None:
        with (
            patch("judge.core.docker_launcher.ensure_sandbox_preflight") as preflight,
            self.assertRaisesRegex(JudgeError, "between 1 and 65535"),
        ):
            run_docker_web(0)

        preflight.assert_not_called()

    def test_background_start_is_detached_and_waits_for_requested_port(self) -> None:
        with (
            patch("judge.core.docker_launcher._container_state", return_value=None),
            patch("judge.core.docker_launcher._ensure_launcher_preflight"),
            patch("judge.core.docker_launcher.verify_local_official_image", return_value=DIGEST),
            patch("judge.core.docker_launcher._prepare_web_service"),
            patch("judge.core.docker_launcher._wait_for_web_service") as wait,
            patch(
                "judge.core.docker_launcher._run_command",
                return_value=completed(stdout="container-id\n"),
            ) as run,
        ):
            state = start_docker_web(9000)

        command = run.call_args.args[0]
        self.assertIn("--detach", command)
        self.assertNotIn("--rm", command)
        self.assertIn("0.0.0.0:9000:9000", command)
        self.assertEqual(
            command[-6:],
            ["--host", "0.0.0.0", "--port", "9000", "--no-open", "--allow-remote-run"],
        )
        self.assertEqual(state["port"], 9000)
        wait.assert_called_once_with(JUDGE_DOCKER_WEB, 9000)

    def test_stop_only_targets_a_running_managed_container(self) -> None:
        state = {
            "status": "running",
            "running": True,
            "container": JUDGE_DOCKER_WEB.container_name,
            "port": 8765,
            "url": "http://127.0.0.1:8765",
            "publishedAddress": "0.0.0.0:8765",
            "workspace": None,
        }
        with (
            patch("judge.core.docker_launcher._container_state", return_value=state),
            patch("judge.core.docker_launcher._run_command", return_value=completed()) as run,
        ):
            stopped = stop_docker_web()

        self.assertEqual(stopped["status"], "stopped")
        run.assert_called_once_with(
            ["docker", "stop", "--time", "10", JUDGE_DOCKER_WEB.container_name],
            "Docker Judge web container stop",
        )

    def test_restart_reuses_saved_port_unless_overridden(self) -> None:
        state = {
            "status": "exited",
            "running": False,
            "container": JUDGE_DOCKER_WEB.container_name,
            "port": 9123,
            "url": "http://127.0.0.1:9123",
            "publishedAddress": "0.0.0.0:9123",
            "workspace": None,
        }
        with (
            patch("judge.core.docker_launcher._container_state", side_effect=[state, None]),
            patch("judge.core.docker_launcher._ensure_launcher_preflight"),
            patch("judge.core.docker_launcher.verify_local_official_image", return_value=DIGEST),
            patch("judge.core.docker_launcher._prepare_web_service"),
            patch("judge.core.docker_launcher._wait_for_web_service"),
            patch(
                "judge.core.docker_launcher._run_command",
                side_effect=[completed(), completed(stdout="new-id\n")],
            ) as run,
        ):
            restarted = restart_docker_web()

        self.assertEqual(restarted["port"], 9123)
        self.assertIn("0.0.0.0:9123:9123", run.call_args_list[-1].args[0])

    def test_status_reports_health_without_mutating_the_container(self) -> None:
        state = {
            "status": "running",
            "running": True,
            "container": JUDGE_DOCKER_WEB.container_name,
            "port": 8765,
            "url": "http://127.0.0.1:8765",
            "publishedAddress": "0.0.0.0:8765",
            "workspace": None,
        }
        with (
            patch("judge.core.docker_launcher._container_state", return_value=state),
            patch("judge.core.docker_launcher._health_matches", return_value=True) as health,
        ):
            result = docker_web_status()

        self.assertTrue(result["healthy"])
        health.assert_called_once_with(JUDGE_DOCKER_WEB, 8765)

    def test_status_refuses_legacy_same_name_container_with_migration_guidance(self) -> None:
        inspection = completed(stdout='[{"Config":{"Labels":{}},"State":{"Running":true}}]')
        with (
            patch("judge.core.docker_launcher._run_command", return_value=inspection),
            self.assertRaisesRegex(JudgeError, "legacy or unrelated container"),
        ):
            docker_web_status()

    def test_problem_studio_mounts_workspace_and_publishes_same_port(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-docker-studio-") as directory:
            workspace = Path(directory).resolve()
            with (
                patch("judge.core.docker_launcher._container_state", return_value=None),
                patch("judge.core.docker_launcher._ensure_launcher_preflight"),
                patch(
                    "judge.core.docker_launcher.verify_local_official_image",
                    return_value=DIGEST,
                ),
                patch("judge.core.docker_launcher._prepare_web_service"),
                patch("judge.core.docker_launcher._wait_for_web_service"),
                patch(
                    "judge.core.docker_launcher._run_command",
                    return_value=completed(stdout="studio-id\n"),
                ) as run,
            ):
                state = start_docker_studio_web(workspace, 9775)

        command = run.call_args.args[0]
        self.assertIn(f"{WORKSPACE_LABEL_KEY}={workspace}", command)
        self.assertIn(f"type=bind,source={workspace},target=/workspace", command)
        self.assertIn("0.0.0.0:9775:9775", command)
        self.assertIn("problem-studio", command)
        self.assertIn("--allow-remote-write", command)
        self.assertEqual(state["workspace"], str(workspace))


class DockerLauncherCliAndReleaseTest(unittest.TestCase):
    def test_parser_exposes_setup_and_web_commands(self) -> None:
        parser = build_parser()
        setup = parser.parse_args(["docker", "setup"])
        web = parser.parse_args(["docker", "web", "--port", "9876"])

        self.assertEqual((setup.command, setup.docker_command), ("docker", "setup"))
        self.assertEqual((web.command, web.docker_command, web.port), ("docker", "web", 9876))
        for action in ("start", "stop", "restart", "status"):
            parsed = parser.parse_args(["docker", "web", action])
            self.assertEqual(parsed.docker_web_action, action)
            studio = parser.parse_args(["docker", "studio", action])
            self.assertEqual(studio.docker_web_action, action)

    def test_dispatch_calls_docker_launcher_services(self) -> None:
        with (
            patch("judge.commands.docker.setup_docker_judge") as setup,
            patch("judge.commands.docker.run_docker_web") as web,
        ):
            self.assertEqual(main(["docker", "setup"]), 0)
            self.assertEqual(main(["docker", "web", "--port", "9876"]), 0)

        setup.assert_called_once_with()
        web.assert_called_once_with(9876)

    def test_dispatch_calls_background_lifecycle_services(self) -> None:
        running = {
            "status": "running",
            "running": True,
            "healthy": True,
            "container": JUDGE_DOCKER_WEB.container_name,
            "url": "http://127.0.0.1:9876",
            "publishedAddress": "0.0.0.0:9876",
        }
        stopped = {**running, "status": "stopped", "running": False, "healthy": False}
        with (
            patch("judge.commands.docker.start_docker_web", return_value=running) as start,
            patch("judge.commands.docker.restart_docker_web", return_value=running) as restart,
            patch("judge.commands.docker.stop_docker_web", return_value=stopped) as stop,
            patch("judge.commands.docker.docker_web_status", return_value=running) as status,
        ):
            self.assertEqual(main(["docker", "web", "start", "--port", "9876"]), 0)
            self.assertEqual(main(["docker", "web", "restart"]), 0)
            self.assertEqual(main(["docker", "web", "status"]), 0)
            self.assertEqual(main(["docker", "web", "stop"]), 0)

        start.assert_called_once_with(9876)
        restart.assert_called_once_with(None)
        status.assert_called_once_with(JUDGE_DOCKER_WEB)
        stop.assert_called_once_with()

    def test_dockerfile_pins_cosign_and_non_root_user(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

        self.assertIn(COSIGN_VERIFIER_IMAGE, dockerfile)
        self.assertIn("ghcr.io/sigstore/cosign/cosign:v3.0.6@sha256:", dockerfile)
        self.assertIn("ubuntu:24.04@sha256:", dockerfile)
        self.assertIn("COPY --from=cosign-bin /ko-app/cosign /usr/local/bin/cosign", dockerfile)
        self.assertIn("useradd --uid 10001 --gid 10001", dockerfile)
        self.assertIn("USER alj", dockerfile)
        self.assertIn("ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS=30000", dockerfile)
        self.assertIn("problems", dockerignore)

    def test_container_tool_compile_floor_is_bounded(self) -> None:
        with patch.dict("os.environ", {"ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS": "30000"}):
            self.assertEqual(effective_tool_compile_timeout_ms(5000), 30000)
            self.assertEqual(effective_tool_compile_timeout_ms(45000), 45000)
        with patch.dict("os.environ", {"ALJ_TOOL_COMPILE_TIMEOUT_MIN_MS": "999999"}):
            self.assertEqual(effective_tool_compile_timeout_ms(5000), 120000)

    def test_release_builds_pushes_and_signs_immutable_multiarch_image(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("packages: write", workflow)
        self.assertIn(
            "docker/build-push-action@10e90e3645eae34f1e60eeb005ba3a3d33f178e8", workflow
        )
        self.assertIn("release tag ${GITHUB_REF_NAME} does not match", workflow)
        self.assertIn("type=semver,pattern={{version}}", workflow)
        self.assertIn("runner: ubuntu-24.04", workflow)
        self.assertIn("runner: ubuntu-24.04-arm", workflow)
        self.assertIn("platform: linux/amd64", workflow)
        self.assertIn("platform: linux/arm64", workflow)
        self.assertNotIn("docker/setup-qemu-action", workflow)
        self.assertIn("push-by-digest=true,name-canonical=true,push=true", workflow)
        self.assertIn("docker buildx imagetools create", workflow)
        self.assertIn("ghcr.io/tony9402/algorithm-local-judge@${IMAGE_DIGEST}", workflow)
        self.assertIn("cosign sign --yes", workflow)
        self.assertIn("needs: verify", workflow)
        self.assertIn("install_local.sh.sigstore.json", workflow)
        self.assertIsNone(re.search(r"uses:\s+[^\s@]+@v\d", workflow))

        ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("docker-e2e:", ci_workflow)
        self.assertIn('ALJ_RUN_DOCKER_TESTS: "1"', ci_workflow)
        self.assertIsNone(re.search(r"uses:\s+[^\s@]+@v\d", ci_workflow))


if __name__ == "__main__":
    unittest.main()
