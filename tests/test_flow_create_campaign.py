"""End-to-end campaign lifecycle acceptance test."""
from datetime import date, timedelta

from helpers import body_data, unique_name, wait_for_build


def test_full_campaign_flow(api, ensure_sender_id, ensure_language):
    response = api.post("/campaigns/", json={
        "name": unique_name("Flow Camp"),
        "sender_id": "mpes_info",
        "channels": ["SMS"],
    })
    assert response.status_code in (200, 201), response.text
    campaign_id = body_data(response)["id"]

    try:
        response = api.post(f"/campaigns/{campaign_id}/content/", json={
            "en": "Hello {{name}}",
            "default_language": ensure_language,
        })
        assert response.status_code in (200, 201), response.text

        response = api.post(f"/campaigns/{campaign_id}/audience/manual/", json={
            "manual_msisdns": ["+251711111111", "+251722222222"],
            "manual_languages": ["en", "en"],
            "default_language": ensure_language,
        })
        assert response.status_code in (200, 201), response.text

        config = body_data(api.get(f"/campaigns/{campaign_id}/audience-config/")).get("id")
        assert config
        response = api.post(f"/audience-configs/{config}/build/", json={})
        assert response.status_code == 202, response.text
        job = body_data(response)
        result = wait_for_build(api, job["job_id"])
        assert result["status"] == "SUCCEEDED", result

        response = api.post(f"/campaigns/{campaign_id}/schedule/", json={
            "schedule_type": "once",
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "time_windows": [{"start": "09:00", "end": "17:00"}],
            "timezone": "UTC",
        })
        assert response.status_code in (200, 201), response.text

        readiness = body_data(api.get(f"/campaigns/{campaign_id}/readiness/"))
        assert readiness["is_ready"] is True, readiness

        response = api.post(f"/campaigns/{campaign_id}/messages/build/", json={
            "round_number": 1,
            "batch_id": f"flow-{campaign_id}-round-1",
        })
        assert response.status_code in (200, 201), response.text
        assert body_data(response)["built"] == 2

        response = api.post(f"/campaigns/{campaign_id}/activate/", json={"build_messages": False})
        assert response.status_code in (200, 201), response.text
        assert body_data(response)["status"] == "active"
    finally:
        api.delete(f"/campaigns/{campaign_id}/hard-delete/")
