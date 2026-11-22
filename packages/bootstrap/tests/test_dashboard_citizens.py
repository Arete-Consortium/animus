"""Tests for the citizens dashboard router and templates."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from animus_bootstrap.dashboard.app import app
from animus_bootstrap.intelligence.citizen_bridge import CitizenBridge, CitizenProposalView


@pytest.fixture()
def client() -> TestClient:
    """TestClient for the dashboard app."""
    return TestClient(app)


def _csrf_headers(client: TestClient) -> dict[str, str]:
    """Prime the CSRF cookie via GET / and return the X-CSRF-Token header."""
    client.get("/")
    token = client.cookies.get("animus_csrf")
    assert token is not None, "CSRF cookie not set"
    return {"X-CSRF-Token": token}


class TestCitizensOverviewPage:
    """Tests for /citizens overview."""

    def test_citizens_page_returns_200(self, client: TestClient) -> None:
        """GET /citizens returns 200."""
        resp = client.get("/citizens")
        assert resp.status_code == 200

    def test_citizens_page_shows_all_citizens(self, client: TestClient) -> None:
        """Overview lists all 5 citizens."""
        resp = client.get("/citizens")
        assert "Architect" in resp.text
        assert "Conversation Designer" in resp.text
        assert "Knowledge Curator" in resp.text
        assert "Test Oracle" in resp.text
        assert "Session Steward" in resp.text

    def test_citizens_page_shows_summary_bar(self, client: TestClient) -> None:
        """Summary bar with counts is visible."""
        resp = client.get("/citizens")
        assert "Total Citizens" in resp.text
        assert "Active" in resp.text
        assert "Pending Proposals" in resp.text

    def test_citizens_page_shows_core_warning_when_unavailable(self, client: TestClient) -> None:
        """Degraded mode banner appears when core is absent."""
        app.state.runtime = None
        with patch.object(CitizenBridge, "_check_core", return_value=False):
            resp = client.get("/citizens")
        assert "not available" in resp.text.lower() or "unavailable" in resp.text.lower()


class TestCitizensProposalsPage:
    """Tests for /citizens/proposals."""

    def test_proposals_page_returns_200(self, client: TestClient) -> None:
        """GET /citizens/proposals returns 200."""
        resp = client.get("/citizens/proposals")
        assert resp.status_code == 200

    def test_proposals_page_shows_filters(self, client: TestClient) -> None:
        """Filter dropdowns are present."""
        resp = client.get("/citizens/proposals")
        assert "Status" in resp.text
        assert "Citizen" in resp.text

    def test_proposals_page_empty_state(self, client: TestClient) -> None:
        """Empty state shown when no proposals."""
        app.state.runtime = None
        resp = client.get("/citizens/proposals")
        assert "No proposals match" in resp.text or "No proposals" in resp.text

    def test_proposals_page_with_mock_proposals(self, client: TestClient) -> None:
        """Proposals render in the table when bridge returns data."""
        fake = CitizenProposalView(
            id="p1",
            title="Test Proposal",
            status="draft",
            source_citizen="architect",
            confidence_score=0.8,
            estimated_effort_hours=4.0,
        )

        with patch.object(CitizenBridge, "list_proposals", return_value=[fake]):
            resp = client.get("/citizens/proposals")
            assert resp.status_code == 200
            assert "Test Proposal" in resp.text


class TestCitizenDetailPage:
    """Tests for /citizens/{name}."""

    def test_citizen_detail_returns_200(self, client: TestClient) -> None:
        """GET /citizens/architect returns 200."""
        resp = client.get("/citizens/architect")
        assert resp.status_code == 200

    def test_citizen_detail_shows_name(self, client: TestClient) -> None:
        """Detail page displays the citizen name."""
        resp = client.get("/citizens/architect")
        assert "Architect" in resp.text

    def test_unknown_citizen_returns_200_with_empty_state(self, client: TestClient) -> None:
        """Unknown citizen name still renders the page."""
        resp = client.get("/citizens/nonexistent")
        assert resp.status_code == 200


class TestCitizenActions:
    """Tests for POST approve/reject/commission."""

    def test_approve_proposal_without_core(self, client: TestClient) -> None:
        """Approving without core returns simulated result."""
        app.state.runtime = None
        headers = _csrf_headers(client)
        resp = client.post(
            "/citizens/proposals/test-id/approve",
            headers=headers,
        )
        assert resp.status_code == 200

    def test_reject_proposal_without_core(self, client: TestClient) -> None:
        """Rejecting without core returns simulated result."""
        app.state.runtime = None
        headers = _csrf_headers(client)
        resp = client.post(
            "/citizens/proposals/test-id/reject",
            headers=headers,
        )
        assert resp.status_code == 200

    def test_commission_proposal_without_core(self, client: TestClient) -> None:
        """Commissioning without core returns error indicator in fragment."""
        app.state.runtime = None
        headers = _csrf_headers(client)
        resp = client.post(
            "/citizens/proposals/test-id/commission",
            headers=headers,
        )
        assert resp.status_code == 200
        # Fallback row renders; error is shown as a warning indicator
        assert "proposal-row-test-id" in resp.text
        assert "commissioned" in resp.text.lower()

    def test_approve_records_event(self, client: TestClient) -> None:
        """Approval POST records an event to the ledger."""
        from animus_bootstrap.intelligence.event_ledger import EventLedger

        ledger = EventLedger()
        runtime = MagicMock()
        runtime.started = True
        runtime.event_ledger = ledger
        app.state.runtime = runtime

        headers = _csrf_headers(client)
        client.post(
            "/citizens/proposals/p-123/approve",
            headers=headers,
        )

        events = ledger.query(event_type="citizen_proposal_approved")
        assert len(events) == 1
        assert events[0]["payload"]["proposal_id"] == "p-123"


class TestCitizensApi:
    """Tests for JSON API endpoints."""

    def test_summary_api_returns_json(self, client: TestClient) -> None:
        """GET /api/citizens/summary returns JSON."""
        resp = client.get("/api/citizens/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "citizens_total" in data
        assert "proposals_total" in data
        assert "core_available" in data

    def test_summary_api_counts_match_registry(self, client: TestClient) -> None:
        """Total citizens equals registry size."""
        resp = client.get("/api/citizens/summary")
        data = resp.json()
        assert data["citizens_total"] == 5

    def test_proposals_api_returns_json(self, client: TestClient) -> None:
        """GET /api/citizens/proposals returns JSON list."""
        resp = client.get("/api/citizens/proposals")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_proposals_api_filters_by_status(self, client: TestClient) -> None:
        """GET /api/citizens/proposals?status=draft filters."""
        resp = client.get("/api/citizens/proposals?status=draft")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_approve_api_returns_json(self, client: TestClient) -> None:
        """POST /api/citizens/proposals/{id}/approve returns JSON."""
        headers = _csrf_headers(client)
        resp = client.post(
            "/api/citizens/proposals/test-id/approve",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_reject_api_returns_json(self, client: TestClient) -> None:
        """POST /api/citizens/proposals/{id}/reject returns JSON."""
        headers = _csrf_headers(client)
        resp = client.post(
            "/api/citizens/proposals/test-id/reject",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_commission_api_returns_json(self, client: TestClient) -> None:
        """POST /api/citizens/proposals/{id}/commission returns JSON."""
        headers = _csrf_headers(client)
        resp = client.post(
            "/api/citizens/proposals/test-id/commission",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data


class TestCitizensFragments:
    """Tests for HTMX pollable fragments."""

    def test_status_cards_fragment_returns_200(self, client: TestClient) -> None:
        """GET /citizens/fragments/status-cards returns 200."""
        resp = client.get("/citizens/fragments/status-cards")
        assert resp.status_code == 200
        assert "Architect" in resp.text

    def test_proposals_table_fragment_returns_200(self, client: TestClient) -> None:
        """GET /citizens/fragments/proposals-table returns 200."""
        resp = client.get("/citizens/fragments/proposals-table")
        assert resp.status_code == 200
        assert "No proposals yet" in resp.text or "proposals" in resp.text.lower()

    def test_proposals_table_fragment_with_mock_data(self, client: TestClient) -> None:
        """Fragment renders proposals when bridge returns data."""
        fake = CitizenProposalView(
            id="p1",
            title="Fragment Proposal",
            status="draft",
            source_citizen="architect",
            confidence_score=0.8,
            estimated_effort_hours=2.0,
        )
        with patch.object(CitizenBridge, "list_proposals", return_value=[fake]):
            resp = client.get("/citizens/fragments/proposals-table")
            assert resp.status_code == 200
            assert "Fragment Proposal" in resp.text


class TestNavigationWiring:
    """Tests that citizens page is linked from base navigation."""

    def test_nav_link_present(self, client: TestClient) -> None:
        """Sidebar contains a link to /citizens."""
        resp = client.get("/")
        assert '/citizens"' in resp.text or "Citizens" in resp.text

    def test_keyboard_shortcut_documented(self, client: TestClient) -> None:
        """Help modal mentions citizens shortcut."""
        resp = client.get("/")
        assert "gci" in resp.text or "citizens" in resp.text.lower()
