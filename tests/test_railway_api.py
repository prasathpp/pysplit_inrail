import unittest

import requests

from railway_api import (
    RailwayApiError,
    extract_schedule_from_html,
    get_schedule_from_page,
    get_trains_between_stations,
)


class FakeResponse:
    def __init__(
        self,
        *,
        payload=None,
        text: str = "",
        error: requests.exceptions.RequestException | None = None,
    ) -> None:
        self._payload = payload
        self.text = text
        self._error = error

    def raise_for_status(self) -> None:
        if self._error:
            raise self._error

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_url = None
        self.last_kwargs = None
        self.headers: dict[str, str] = {}

    def get(self, url, **kwargs):
        self.last_url = url
        self.last_kwargs = kwargs
        return self.response

    def post(self, url, **kwargs):
        self.last_url = url
        self.last_kwargs = kwargs
        return self.response


class RailwayApiTests(unittest.TestCase):
    def test_get_trains_between_stations_builds_ixigo_request_and_normalizes_response(self) -> None:
        session = FakeSession(
            FakeResponse(
                payload={
                    "data": {
                        "errorCode": 0,
                        "trainList": [
                            {
                                "trainName": "KAVERI EXPRESS",
                                "trainNumber": "16021",
                                "fromStnName": "Chennai Central",
                                "toStnName": "Mysore Junction",
                                "departureTime": "21:15",
                                "arrivalTime": "06:40",
                                "duration": 565,
                                "avlClassesSorted": ["SL", "3A"],
                                "availabilityCacheForQuota": {
                                    "SL": {
                                        "availabilityDisplayName": "AVL 36",
                                        "availability": "AVAILABLE-0036",
                                        "prediction": "Available",
                                        "fare": "310",
                                        "quota": "SS",
                                    }
                                },
                                "availabilityCache": {
                                    "SL": {
                                        "availabilityDisplayName": "WL 33",
                                        "availability": "GNWL52/WL33",
                                        "prediction": "90% Chance",
                                        "fare": "310",
                                        "quota": "GN",
                                    }
                                },
                            }
                        ],
                    }
                }
            )
        )

        payload = get_trains_between_stations(
            "mas",
            "mys",
            "31-07-2026",
            quota="ss",
            session=session,
            timeout=3,
        )

        self.assertEqual(session.last_kwargs["params"]["sourceStationCode"], "MAS")
        self.assertEqual(session.last_kwargs["params"]["destinationStationCode"], "MYS")
        self.assertEqual(session.last_kwargs["params"]["quota"], "SS")
        self.assertEqual(session.last_kwargs["timeout"], 3)
        self.assertEqual(payload["provider"], "ixigo")
        train = payload["train_between_stations"][0]
        self.assertEqual(train["train_name"], "KAVERI EXPRESS")
        self.assertEqual(train["duration"], "9:25")
        seat_status = train["sa_data"][0]["seat_availibility"][0]
        self.assertEqual(seat_status["Class - SL"], "AVL 36")
        self.assertEqual(seat_status["quota"], "SS")

    def test_get_trains_between_stations_builds_railyatri_request_params(self) -> None:
        session = FakeSession(FakeResponse(payload={"success": True}))

        payload = get_trains_between_stations(
            "mas",
            "mys",
            "31-07-2026",
            quota="gn",
            provider="railyatri",
            session=session,
            timeout=3,
        )

        self.assertEqual(payload, {"success": True, "provider": "railyatri"})
        self.assertEqual(session.last_kwargs["params"]["from"], "MAS")
        self.assertEqual(session.last_kwargs["params"]["to"], "MYS")
        self.assertEqual(session.last_kwargs["params"]["journey_quota"], "GN")
        self.assertEqual(session.last_kwargs["timeout"], 3)


    def test_get_trains_between_stations_rejects_bad_date(self) -> None:
        with self.assertRaises(ValueError):
            get_trains_between_stations("MAS", "MYS", "2026-07-31", session=FakeSession(FakeResponse()))

    def test_get_trains_between_stations_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValueError):
            get_trains_between_stations(
                "MAS",
                "MYS",
                "31-07-2026",
                provider="unknown",
                session=FakeSession(FakeResponse()),
            )

    def test_extract_schedule_from_html(self) -> None:
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"trainTimeTable":{"train_number":"12345"}}}}'
            "</script>"
        )

        schedule = extract_schedule_from_html(html)

        self.assertEqual(schedule["train_number"], "12345")

    def test_extract_schedule_from_html_errors_when_missing(self) -> None:
        with self.assertRaises(RailwayApiError):
            extract_schedule_from_html("<html></html>")

    def test_get_schedule_from_page_uses_train_number_url(self) -> None:
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props":{"pageProps":{"trainTimeTable":{"train_number":"12164"}}}}'
            "</script>"
        )
        session = FakeSession(FakeResponse(text=html))

        schedule = get_schedule_from_page("12164", session=session, timeout=5)

        self.assertEqual(schedule["train_number"], "12164")
        self.assertIn("/12164", session.last_url)
        self.assertEqual(session.last_kwargs["timeout"], 5)


if __name__ == "__main__":
    unittest.main()
