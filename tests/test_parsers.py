"""
Testes dos parsers de HTML das fontes (crawlers).

Rodam OFFLINE contra fixtures HTML salvas em tests/fixtures/, sem acessar a
rede. Requerem beautifulsoup4 instalado (pip install -r requirements.txt).

    python -m pytest tests/ -q
    # ou, sem pytest:
    python tests/test_parsers.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def test_github_search_parsing():
    from coletor.sources.github import GitHubSource
    ids = GitHubSource().parse_listing(_read("github_search.html"))
    assert "torvalds/linux" in ids
    assert "facebook/react" in ids
    assert "vuejs/vue" in ids
    # reservados e não-repos são filtrados; duplicados removidos
    assert "search/q=stars" not in ids
    assert ids.count("torvalds/linux") == 1
    assert all("/" in i and len(i.split("/")) == 2 for i in ids)


def test_github_repo_parsing():
    from coletor.sources.github import GitHubSource
    html = _read("github_repo.html")
    repo = GitHubSource().parse_detail("torvalds/linux", html)
    assert repo["full_name"] == "torvalds/linux"
    assert repo["source"] == "github_html"
    assert repo["stars"] == 180000
    assert repo["forks"] == 53200
    assert repo["open_issues"] == 450
    assert repo["language"] == "C"
    assert "kernel" in repo["topics"] and "linux" in repo["topics"]
    assert repo["default_branch"] == "master"
    assert "GPL" in (repo["license_name"] or "")
    assert repo["description"] == "Linux kernel source tree"
    readme = GitHubSource().parse_readme(html)
    assert readme and "Linux kernel readme body" in readme


def test_sourceforge_directory_parsing():
    from coletor.sources.sourceforge import SourceForgeSource
    ids = SourceForgeSource().parse_listing(_read("sourceforge_directory.html"))
    assert "mingw" in ids
    assert "reactos" in ids
    assert "sevenzip" in ids
    assert ids.count("mingw") == 1


def test_sourceforge_project_parsing():
    from coletor.sources.sourceforge import SourceForgeSource
    html = _read("sourceforge_project.html")
    repo = SourceForgeSource().parse_detail("mingw", html)
    assert repo["full_name"] == "sourceforge/mingw"
    assert repo["source"] == "sourceforge"
    assert repo["owner_login"] == "sourceforge"
    assert "MinGW" in repo["name"]
    assert repo["description"] and "GNU Compiler" in repo["description"]
    assert repo["homepage"] == "https://osdn.net/projects/mingw/"
    readme = SourceForgeSource().parse_readme(html)
    assert readme and "programming tool set" in readme


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passaram.")
    sys.exit(1 if failed else 0)
