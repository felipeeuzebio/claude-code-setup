import json
from pathlib import Path

from claude_code_setup.mcp.config import build_plan, github_add_command, is_registered, merge_and_write


def test_context7_always_ready() -> None:
    ready, _, _ = build_plan({})["context7"]
    assert ready is True


def test_github_is_left_to_the_user() -> None:
    # The user registers GitHub with their own PAT; setup never handles it.
    assert "github" not in build_plan({"GITHUB_TOKEN": "abc"})


def test_github_add_command_has_a_pat_placeholder_and_the_real_server() -> None:
    cmd = github_add_command()
    assert cmd.startswith("claude mcp add github --scope user ")
    assert "GITHUB_PERSONAL_ACCESS_TOKEN=<your-PAT>" in cmd
    assert cmd.endswith("-- npx -y @modelcontextprotocol/server-github")


def test_is_registered_reads_claude_json(tmp_path: Path) -> None:
    env = {"CLAUDE_HOME": str(tmp_path)}
    assert is_registered("github", env) is False

    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"github": {"command": "npx"}}}), encoding="utf-8"
    )
    assert is_registered("github", env) is True
    assert is_registered("context7", env) is False


def test_browser_use_and_lightpanda_gated_on_flags() -> None:
    assert build_plan({})["browser-use"][0] is False
    assert build_plan({"HAS_UVX": "true"})["browser-use"][0] is True
    assert build_plan({})["lightpanda"][0] is False
    assert build_plan({"HAS_LIGHTPANDA": "1"})["lightpanda"][0] is True


def test_codegraph_has_no_plan_entry() -> None:
    assert "codegraph" not in build_plan({})


def test_merge_and_write_creates_new_file(tmp_path: Path, capsys) -> None:
    target = tmp_path / ".claude.json"
    merge_and_write(env={}, target_path=target)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert "context7" in data["mcpServers"]
    assert "github" not in data["mcpServers"]
    assert "codegraph" not in data["mcpServers"]

    out = capsys.readouterr().out
    assert "context7" in out
    assert "Skipped:" in out
    assert "github" not in out


def test_merge_and_write_backs_up_existing_and_preserves_other_keys(
    tmp_path: Path,
) -> None:
    target = tmp_path / ".claude.json"
    target.write_text(
        json.dumps({"mcpServers": {"custom": {"command": "x"}}, "otherTopLevelKey": 1}),
        encoding="utf-8",
    )

    merge_and_write(env={}, target_path=target)

    backups = list(tmp_path.glob(".claude.json.bak-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8"))["mcpServers"] == {
        "custom": {"command": "x"}
    }

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["otherTopLevelKey"] == 1
    assert data["mcpServers"]["custom"] == {"command": "x"}
    assert "context7" in data["mcpServers"]
