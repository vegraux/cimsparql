[![PyPI version](https://img.shields.io/pypi/v/cimsparql)](https://pypi.org/project/cimsparql/)
[![Python Versions](https://img.shields.io/pypi/pyversions/cimsparql)](https://pypi.org/project/cimsparql/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![](https://github.com/statnett/data_cache/workflows/Tests/badge.svg)](https://github.com/statnett/cimsparql/actions?query=workflow%3ATests)
[![codecov](https://codecov.io/gh/statnett/cimsparql/branch/master/graph/badge.svg)](https://codecov.io/gh/statnett/cimsparql)

# CIMSPARQL Query CIM data using sparql

This Python package provides functionality for reading/parsing cim data from
either xml files or GraphDB into Python memory as pandas dataframes.

The package provides a set of predefined functions/queries to load CIM data
such generator or branch data, though the user can easiliy extend or define
their own queries.

## Usage

### Load data using predefined functions/queries

```python
>>> from cimsparql.graphdb import GraphDBClient
>>> from cimsparql.url import service
>>> gdbc = GraphDBClient(service(repo='<repo>', server=127.0.0.1:7200))
>>> ac_lines = gdbc.ac_lines(limit=3)
>>> print(ac_lines[['name', 'x', 'r', 'bch']])
         name       x       r       bch
0  <branch 1>  1.9900  0.8800  0.000010
1  <branch 2>  1.9900  0.8800  0.000010
2  <branch 3>  0.3514  0.1733  0.000198
```

In the example above the client will query repo "<repo>" in the default server
[GraphDB](https://graphdb.ontotext.com) for AC line values.

### Inspect/view predefined queries

To see the actual sparql use the `dry_run` option:

```python
>>> from cimsparql.queries import ac_line_query
>>> print(ac_line_query(limit=3, dry_run=True))
```

The resulting string contains all the prefix's available in the Graphdb repo
making it easier to copy and past to graphdb. Note that the prefixes are *not*
required in the user specified quires described below.

The `dry_run` option is available for all the predefined queries.

### Load data using user specified queries

```python
>>> query = 'SELECT ?mrid where { ?mrid rdf:type cim:ACLineSegment } limit 2'
>>> query_result = gdbc.get_table(query)
>>> print(query_result)
```

### List of available repos at the server

```python
>>> from cimsparql.url import GraphDbConfig
>>> print(GraphDbConfig().repos)
```

### Prefix and namespace

Available namespace for current graphdb client (`gdbc` in the examples above),
which can be used in queries (such as `rdf` and `cim`) can by found by

```python
>>> print(gdbc.ns)
{'wgs': 'http://www.w3.org/2003/01/geo/wgs84_pos#',
 'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
 'owl': 'http://www.w3.org/2002/07/owl#',
 'cim': 'http://iec.ch/TC57/2010/CIM-schema-cim15#',
 'gn': 'http://www.geonames.org/ontology#',
 'xsd': 'http://www.w3.org/2001/XMLSchema#',
 'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
 'SN': 'http://www.statnett.no/CIM-schema-cim15-extension#',
 'ALG': 'http://www.alstom.com/grid/CIM-schema-cim15-extension#'}
```
