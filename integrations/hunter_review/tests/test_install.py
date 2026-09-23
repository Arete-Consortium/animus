"""Installation failures must leave the previous service and snapshots available."""

import pytest

from integrations.hunter_review.install_local import CONTAINER, replace_service


class DockerFixture:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []
        self.containers = {CONTAINER: {"id": "original", "running": True}}

    def __call__(self, *args):
        self.calls.append(args)
        command = args[0]
        stage = None
        if command == "create":
            name = args[args.index("--name") + 1]
            stage = "prepare" if "install-" in name else "create_replacement"
        elif command == "cp":
            stage = "copy"
        elif command == "exec":
            stage = "health" if args[1] == CONTAINER else "validate"
        elif command == "start" and args[1] == CONTAINER:
            if self.containers[CONTAINER]["id"] != "original":
                stage = "start_replacement"
        if self.failure is not None and stage == self.failure:
            self.failure = None
            raise RuntimeError(f"injected {stage} failure")
        if command == "ps":
            return CONTAINER if CONTAINER in self.containers else ""
        if command == "inspect":
            return "hunter-review"
        if command == "create":
            self.containers[name] = {"id": name, "running": False}
        elif command == "start":
            self.containers[args[1]]["running"] = True
        elif command == "stop":
            self.containers[args[-1]]["running"] = False
        elif command == "rename":
            self.containers[args[2]] = self.containers.pop(args[1])
        elif command == "rm":
            self.containers.pop(args[-1], None)
        return ""


@pytest.mark.parametrize(
    "failure", ["prepare", "copy", "validate", "create_replacement", "start_replacement", "health"]
)
def test_failed_replacement_preserves_working_service(failure):
    docker = DockerFixture(failure)
    with pytest.raises(RuntimeError, match="injected"):
        replace_service(docker)
    assert docker.containers[CONTAINER] == {"id": "original", "running": True}
    assert len(docker.containers) == 1
    mounts = [arg for call in docker.calls for arg in call if "src=" in arg]
    assert not any("src=animus-hunter-review-sources," in m for m in mounts)
    assert not any("src=animus-hunter-review-config," in m for m in mounts)


def test_replacement_is_prepared_before_stopping_old_service():
    docker = DockerFixture()
    replace_service(docker)
    assert docker.containers[CONTAINER]["running"]
    assert docker.containers[CONTAINER]["id"] != "original"
    assert len(docker.containers) == 1
    stop_index = docker.calls.index(("stop", CONTAINER))
    create_index = next(
        i
        for i, call in enumerate(docker.calls)
        if call[0] == "create" and "next-" in call[call.index("--name") + 1]
    )
    assert create_index < stop_index
    assert any(call[0] == "cp" for call in docker.calls[:stop_index])
