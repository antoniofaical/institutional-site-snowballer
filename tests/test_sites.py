import pytest

from institutional_site_snowballer.domain.sites import select_sites


def test_duplicates_keep_first_input_and_alias_selection():
    sites = [
        {"name": "Company", "url": "https://company.test/"},
        {"name": "Alias", "url": "http://www.company.test?utm_source=x"},
        {"name": "Company", "url": "https://other.test/"},
    ]
    selected = select_sites(sites, ["Alias"])
    assert selected.sites == [sites[0]]
    assert selected.input_count == 3
    assert selected.duplicates_skipped == 2


@pytest.mark.parametrize("names", [("A B", "A-B"), ("Case", "case"), ("Á", "A")])
def test_directory_collisions(names):
    with pytest.raises(ValueError, match="collide"):
        select_sites(
            [
                {"name": names[0], "url": "https://a.test/"},
                {"name": names[1], "url": "https://b.test/"},
            ]
        )


@pytest.mark.parametrize("name", ["batch.json", "CON", "NUL.txt", "com1", "LPT9"])
def test_reserved_output_names(name):
    with pytest.raises(ValueError):
        select_sites([{"name": name, "url": "https://a.test/"}])


@pytest.mark.parametrize(
    "value",
    [
        {},
        [],
        [{"name": " "}],
        [{"name": "x", "url": "https://"}],
        [{"name": "x", "url": "file:///tmp/site"}],
    ],
)
def test_invalid_input(value):
    with pytest.raises((ValueError, TypeError)):
        select_sites(value)


def test_unknown_selection():
    with pytest.raises(ValueError, match="Unknown"):
        select_sites([{"name": "x", "url": "https://x.test/"}], ["missing"])
