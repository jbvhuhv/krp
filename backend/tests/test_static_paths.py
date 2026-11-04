"""前端静态托管的安全边界：路径穿越必须被拦住。

背景：SPA 回退曾直接 ``os.path.join(root, full_path)`` + ``isfile`` 就返回文件，
而路由参数 ``{full_path:path}`` 会原样接收 ``../``（uvicorn 还会把 %2F 解码成 /），
于是 ``/..%2F..%2Fbackend%2F.env`` / ``/..%2Fkrp.db`` 可以读走密钥与整个业务库。
"""

from app.main import _resolve_static_file


def test_allows_file_inside_root(tmp_path):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    assert _resolve_static_file(str(root), "index.html")
    assert _resolve_static_file(str(root), "assets/app.js")


def test_blocks_parent_traversal(tmp_path):
    root = tmp_path / "dist"
    root.mkdir()
    (root / "index.html").write_text("ok", encoding="utf-8")
    secret = tmp_path / "secret.env"
    secret.write_text("SECRET_KEY=leaked", encoding="utf-8")

    assert _resolve_static_file(str(root), "../secret.env") is None
    assert _resolve_static_file(str(root), "../../../../etc/passwd") is None


def test_blocks_sibling_dir_with_same_prefix(tmp_path):
    """startswith 式的校验会被 dist-evil 这类同级目录绕过，这里必须挡住。"""
    root = tmp_path / "dist"
    root.mkdir()
    (tmp_path / "dist-evil").mkdir()
    (tmp_path / "dist-evil" / "payload.txt").write_text("x", encoding="utf-8")

    assert _resolve_static_file(str(root), "../dist-evil/payload.txt") is None


def test_blocks_absolute_path(tmp_path):
    root = tmp_path / "dist"
    root.mkdir()
    outside = tmp_path / "krp.db"
    outside.write_text("db", encoding="utf-8")

    assert _resolve_static_file(str(root), str(outside)) is None


def test_returns_none_for_missing_or_empty(tmp_path):
    root = tmp_path / "dist"
    root.mkdir()

    assert _resolve_static_file(str(root), "") is None
    assert _resolve_static_file(str(root), "index.html") is None
    assert _resolve_static_file(str(root), "a\x00b") is None
