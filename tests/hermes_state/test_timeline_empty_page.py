"""An empty timeline page still reports its total and sees later appends."""

import pytest

from hermes_state import SessionDB
from hermes_state_timeline import get_session_timeline


@pytest.mark.parametrize("legacy", [False, True])
def test_empty_timeline_page_keeps_totals_and_refreshes_after_append(tmp_path, monkeypatch, legacy):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    with SessionDB(db_path=tmp_path / "state.db") as db:
        db.create_session(session_id="timeline", source="desktop")
        db.append_message("timeline", role="user", content="[IMPORTANT: Background process 1 completed]", timestamp=1)

        def read(after=0):
            if legacy:
                db._write_sql("UPDATE messages SET display_order = NULL, display_identity = NULL")
            return get_session_timeline(db, "timeline", limit=1, after_row_id=after)

        assert read() == {
            "entries": [], "pagination": {
                "limit": 1, "after_row_id": 0, "returned": 0, "total": 0,
                "has_more": False, "next_cursor": None,
            },
        }
        first = db.append_message("timeline", role="user", content="First question", timestamp=10)
        assert read(first) == {
            "entries": [], "pagination": {
                "limit": 1, "after_row_id": first, "returned": 0, "total": 1,
                "has_more": False, "next_cursor": None,
            },
        }
        second = db.append_message("timeline", role="user", content="New question", timestamp=20)
        assert read(first) == {
            "entries": [{"row_id": second, "preview": "New question", "timestamp": 20}],
            "pagination": {
                "limit": 1, "after_row_id": first, "returned": 1, "total": 2,
                "has_more": False, "next_cursor": None,
            },
        }
