from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def migration_scripts() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_revision_graph_is_single_linear_chain() -> None:
    scripts = migration_scripts()
    heads = scripts.get_heads()
    bases = scripts.get_bases()
    revisions = list(scripts.walk_revisions(base="base", head="heads"))
    revision_ids = {revision.revision for revision in revisions}
    children_by_revision = {revision_id: [] for revision_id in revision_ids}

    assert len(heads) == 1
    assert len(bases) == 1

    for revision in revisions:
        down_revision = revision.down_revision
        if down_revision is None:
            continue
        assert isinstance(down_revision, str), "Alembic branch/merge revisions are not expected"
        assert down_revision in revision_ids
        children_by_revision[down_revision].append(revision.revision)

    head = heads[0]
    assert children_by_revision[head] == []
    for revision_id, children in children_by_revision.items():
        if revision_id != head:
            assert len(children) == 1

    current = head
    walked: list[str] = []
    while current is not None:
        revision = scripts.get_revision(current)
        assert revision is not None
        walked.append(revision.revision)
        down_revision = revision.down_revision
        assert down_revision is None or isinstance(down_revision, str)
        current = down_revision

    assert walked == [revision.revision for revision in revisions]
    assert walked[-1] == bases[0]


def test_alembic_files_match_revision_ids_and_export_hooks() -> None:
    for revision in migration_scripts().walk_revisions(base="base", head="heads"):
        path = Path(revision.path)

        assert path.name.startswith(f"{revision.revision}_")
        assert callable(getattr(revision.module, "upgrade", None))
        assert callable(getattr(revision.module, "downgrade", None))
