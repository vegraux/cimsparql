import asyncio
import os
import re
from base64 import b64encode
from http import HTTPStatus
from typing import Callable, List

import httpx
import pandas as pd
import pytest
import requests
import t_utils.common as t_common
import t_utils.custom_models as t_custom
from pytest_httpserver import HeaderValueMatcher

from cimsparql.graphdb import (
    AsyncGraphDBClient,
    GraphDBClient,
    RepoInfo,
    ServiceConfig,
    config_bytes_from_template,
    confpath,
    data_row,
    new_repo,
    repos,
)
from cimsparql.model import Model, SingleClientModel
from cimsparql.type_mapper import TypeMapper


async def collect_data(model: Model) -> List[pd.DataFrame]:
    result = await asyncio.gather(
        model.ac_lines(),
        model.borders(),
        model.branch_node_withdraw(),
        model.bus_data(),
        model.connections(),
        model.converters(),
        model.coordinates(),
        model.disconnected(),
        model.dc_active_flow(),
        model.exchange("NO|SE"),
        model.full_model(),
        model.hvdc_converter_bidzones(),
        model.loads(),
        model.market_dates(),
        model.powerflow(),
        model.regions(),
        model.series_compensators(),
        model.station_group_codes_and_names(),
        model.substation_voltage_level(),
        model.synchronous_machines(),
        model.three_winding_transformers(),
        model.transformer_windings(),
        model.transformers_connected_to_converter(),
        model.transformers(),
        model.two_winding_transformers(),
        model.wind_generating_units(),
    )
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("test_model", t_custom.all_custom_models())
async def test_not_empty(test_model: t_common.ModelTest):
    model = test_model.model
    if not model:
        pytest.skip("Require access to GraphDB")
    dfs = await collect_data(model)

    for i, df in enumerate(dfs):
        assert not df.empty, f"Failed for dataframe {i}"


@pytest.fixture
def model() -> SingleClientModel:
    test_model = t_custom.combined_model()
    if not test_model.model:
        pytest.skip("Require access to GraphDB")
    return test_model.model


def test_cimversion(model: SingleClientModel):
    assert model.cim_version == 16


@pytest.mark.asyncio
async def test_regions(model: SingleClientModel):
    regions = await model.regions()
    assert regions.groupby("region").count().loc["NO", "name"] > 16


@pytest.mark.asyncio
async def test_hvdc_converters_bidzones(model: SingleClientModel):
    df = await model.hvdc_converter_bidzones()

    corridors = set(zip(df["from_area"], df["to_area"]))

    # Check data quality in the models
    expect_corridors = {("SE4", "SE3"), ("NO2", "DE"), ("NO2", "DK1"), ("NO2", "GB"), ("NO2", "NL")}
    assert expect_corridors.issubset(corridors)


@pytest.mark.asyncio
async def test_windings(model: SingleClientModel):
    windings = await model.transformers(region="NO")
    assert windings.shape[1] == 9


@pytest.mark.skipif(os.getenv("GRAPHDB_SERVER") is None, reason="Need graphdb server to run")
@pytest.mark.asyncio
async def test_borders_no(model: SingleClientModel):
    borders = await model.borders(region="NO")
    assert (borders[["area_1", "area_2"]] == "NO").any(axis=1).all()
    assert (borders["area_1"] != borders["area_2"]).all()


def test_data_row():
    cols = ["a", "b", "c", "d", "e"]
    rows = [{"a": 1, "b": 2}, {"c": 3, "d": 4}, {"a": 5, "b": 6}, {"e": 7}]
    assert not set(data_row(cols, rows)).symmetric_difference(cols)


def test_data_row_missing_column():
    cols = ["a", "b", "c", "d", "e"]
    rows = [{"a": 1, "b": 2}, {"c": 3}, {"a": 5, "b": 6}, {"e": 7}]
    assert set(data_row(cols, rows).keys()).symmetric_difference(cols) == {"d"}


def test_dtypes(model: SingleClientModel):
    mapper = TypeMapper(model.client.service_cfg)
    df = model.client.get_table(mapper.query)[0]
    assert df["sparql_type"].isna().sum() == 0


def test_prefix_resp_not_ok(monkeypatch):
    resp = requests.Response()
    resp.status_code = 401
    resp.reason = "Something went wrong"
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: resp)

    with pytest.raises(RuntimeError) as exc:
        GraphDBClient(ServiceConfig(server="some-serever")).get_prefixes()
    assert resp.reason in str(exc)
    assert str(resp.status_code) in str(exc)


def test_conf_bytes_from_template():
    template = confpath() / "native_store_config_template.ttl"

    conf_bytes = config_bytes_from_template(template, {"repo": "test_repo"})
    conf_str = conf_bytes.decode("utf8")
    assert 'rep:repositoryID "test_repo"' in conf_str


@pytest.mark.asyncio
async def test_create_delete_repo():
    url = t_common.rdf4j_url()

    # Check if it is possible to make contact
    try:
        resp = httpx.get("http://" + url)
        if resp.status_code not in [HTTPStatus.OK, HTTPStatus.FOUND] and not os.getenv("CI"):
            pytest.skip("Could not contact RDF4J server")
    except Exception as exc:
        if os.getenv("CI"):
            pytest.fail(f"{exc}")
        else:
            pytest.skip(f"{exc}")
    repo = "test_repo"
    template = confpath() / "native_store_config_template.ttl"
    conf_bytes = config_bytes_from_template(template, {"repo": repo})
    service_cfg = ServiceConfig(repo, "http", url)
    current_repos = await repos(service_cfg)

    assert "test_repo" not in [i.repo_id for i in current_repos]

    # protocol is added internally. Thus, skip from t_common.rdf4j_url
    client = new_repo(url, repo, conf_bytes, protocol="http")
    current_repos = await repos(service_cfg)
    assert "test_repo" in [i.repo_id for i in current_repos]

    client.delete_repo()
    current_repos = await repos(service_cfg)
    assert "test_repo" not in [i.repo_id for i in current_repos]


@pytest.mark.asyncio
async def test_repos_with_auth(httpserver):
    response_json = {
        "results": {
            "bindings": [
                {
                    "uri": {"value": "uri"},
                    "id": {"value": "id"},
                    "title": {"value": "title"},
                    "readable": {"value": "true"},
                    "writable": {"value": "false"},
                }
            ]
        }
    }

    matcher = HeaderValueMatcher({"authorization": lambda value, expect: expect == value})
    user, password = "user", "password"
    encoded_user_passwd = b64encode(bytes(f"{user}:{password}", "utf8")).decode("utf8")
    httpserver.expect_request(
        "/repositories",
        headers={"authorization": f"Basic {encoded_user_passwd}"},
        header_value_matcher=matcher,
    ).respond_with_json(response_json)
    url = httpserver.url_for("/repositories")

    matches = re.match(r"^([a-z]+):\/\/([a-z:0-9]+)", url)
    protocol, server = matches.groups()

    cfg = ServiceConfig("repo", server=server, protocol=protocol, user=user, passwd=password)
    repo_info = await repos(cfg)

    expect = RepoInfo("uri", "id", "title", True, False)
    assert repo_info == [expect]


def test_update_prefixes(monkeypatch):
    monkeypatch.setattr(GraphDBClient, "get_prefixes", lambda *args: {})
    client = GraphDBClient(ServiceConfig(server="some-server"))
    assert client.prefixes == {}

    new_pref = {"eq": "http://eq"}
    client.update_prefixes(new_pref)
    assert client.prefixes == new_pref


@pytest.mark.parametrize("graphdb_client", [GraphDBClient, AsyncGraphDBClient])
def test_custom_headers(graphdb_client: Callable):
    custom_headers = {"my_header": "my_header_value"}
    client = graphdb_client(ServiceConfig(server="some-server"), custom_headers)
    assert client.sparql.customHttpHeaders == custom_headers
