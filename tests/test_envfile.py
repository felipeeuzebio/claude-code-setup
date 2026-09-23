from pathlib import Path

from claude_code_setup.core.envfile import load_env


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(content, encoding="utf-8")
    return p


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_env(tmp_path / "nope.env") == {}


def test_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    p = _write(tmp_path, "\n# a comment\n   \nKEY=value\n")
    assert load_env(p) == {"KEY": "value"}


def test_strips_key_whitespace(tmp_path: Path) -> None:
    p = _write(tmp_path, "  KEY  =value\n")
    assert load_env(p) == {"KEY": "value"}


def test_preserves_unquoted_spaces_and_backslashes_byte_for_byte(tmp_path: Path) -> None:
    # The whole reason this isn't `source`d as shell: a Windows-style path
    # with a space and backslashes must survive untouched.
    p = _write(tmp_path, r"OBSIDIAN_VAULT_PATH=C:\Users\you\Documents\My Vault" + "\n")
    assert load_env(p) == {"OBSIDIAN_VAULT_PATH": r"C:\Users\you\Documents\My Vault"}


def test_strips_one_matching_layer_of_double_quotes(tmp_path: Path) -> None:
    p = _write(tmp_path, 'KEY="quoted value"\n')
    assert load_env(p) == {"KEY": "quoted value"}


def test_strips_one_matching_layer_of_single_quotes(tmp_path: Path) -> None:
    p = _write(tmp_path, "KEY='quoted value'\n")
    assert load_env(p) == {"KEY": "quoted value"}


def test_mismatched_quotes_are_left_alone(tmp_path: Path) -> None:
    p = _write(tmp_path, "KEY=\"mismatched'\n")
    assert load_env(p) == {"KEY": "\"mismatched'"}


def test_value_with_embedded_equals_keeps_the_rest(tmp_path: Path) -> None:
    p = _write(tmp_path, "KEY=a=b=c\n")
    assert load_env(p) == {"KEY": "a=b=c"}


def test_crlf_line_endings(tmp_path: Path) -> None:
    p = _write(tmp_path, "KEY=value\r\n")
    assert load_env(p) == {"KEY": "value"}


def test_line_without_equals_is_ignored(tmp_path: Path) -> None:
    p = _write(tmp_path, "not-a-var\nKEY=value\n")
    assert load_env(p) == {"KEY": "value"}
