"""Synthetic manuscript and submitted report; used only by browser tests."""
import json
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_staff_governance import StaffGovernanceTests
from app import app
from models import db
from governance_models import StaffPeerReview

case = StaffGovernanceTests()
case.setUp()
try:
    editor = case.member('associate_editor', case.journal.id)
    reviewer = case.member('reviewer', case.journal.id)
    item, _ = case.manuscript(editor)
    review = StaffPeerReview(manuscript_id=item.id, reviewer_id=reviewer.id,
                            version_number=1, due_on=date.today())
    db.session.add(review); db.session.commit()
    case.signin(reviewer.admin)
    case.post(f'/admin/pareceres/{review.id}', action='accept', no_conflict='on')
    report = 'Parecer científico entregue: métodos consistentes, corrigir a discussão. ' * 3
    result = case.post(f'/admin/pareceres/{review.id}', action='submit', report=report, recommendation='minor_revision')
    assert result.status_code == 302 and review.status == 'submitted'
    case.signin(editor.admin)
    with case.client.session_transaction() as state:
        cookie = app.session_interface.get_signing_serializer(app).dumps(dict(state))
    print(json.dumps(dict(cookie=cookie, manuscript_id=item.id, report=report.strip())))
finally:
    case.tearDown()
