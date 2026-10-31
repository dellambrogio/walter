from fastapi.testclient import TestClient

from walter.main import app
from walter.photos import MAX_PHOTOS, Photo, plain, spread, to_photo


def photo(position: float, distance_m: int) -> Photo:
    return Photo(
        title="t",
        thumb="",
        large="",
        page="",
        lon=0,
        lat=0,
        author="a",
        licence="CC0",
        licence_url=None,
        description="",
        position=position,
        distance_m=distance_m,
    )


def test_plain_strips_commons_html() -> None:
    assert plain('<a href="//commons.wikimedia.org/wiki/User:X">Jane &amp; Joe</a>\n') == "Jane & Joe"


def test_spread_keeps_order_and_prefers_photos_near_the_trail() -> None:
    photos = [photo(i / 100, distance_m=i % 7) for i in range(100)]
    picked = spread(photos)
    assert len(picked) == MAX_PHOTOS
    assert [p.position for p in picked] == sorted(p.position for p in picked)


def test_only_photographs_with_licence_and_coordinates() -> None:
    page = {
        "title": "File:Alp.jpg",
        "coordinates": [{"lat": 46.9, "lon": 9.0}],
        "imageinfo": [
            {
                "mime": "image/jpeg",
                "thumburl": "https://upload.wikimedia.org/x/800px-Alp.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Alp.jpg",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "Artist": {"value": "<b>Jane</b>"},
                },
            }
        ],
    }
    p = to_photo(page)
    assert p and p.title == "Alp" and p.author == "Jane" and p.large.endswith("/1600px-Alp.jpg")
    assert to_photo({**page, "imageinfo": [{**page["imageinfo"][0], "mime": "image/tiff"}]}) is None
    assert to_photo({**page, "coordinates": None}) is None


def test_unknown_stage_is_404() -> None:
    assert TestClient(app).get("/api/stages/nope/photos").status_code == 404
