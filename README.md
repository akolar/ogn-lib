# OGN Lib

[![Build Status](https://travis-ci.org/akolar/ogn-lib.svg?branch=master)](https://travis-ci.org/akolar/ogn-lib) [![codecov](https://codecov.io/gh/akolar/ogn-lib/branch/master/graph/badge.svg)](https://codecov.io/gh/akolar/ogn-lib) [![PyPI version](https://badge.fury.io/py/OGN-lib.svg)](https://badge.fury.io/py/OGN-lib)


## Overview

OGN Lib is an easily extendable library for communication with the [Open Glider
Network](http://wiki.glidernet.org/)'s APRS servers.

The libray is MIT licensed and uses no external dependencies.


## Quick example

```
from ogn_lib import OgnClient, Parser


def callback(data):
    print(data)

client = OgnClient('N0CALL')
client.connect()
client.receive(callback, parser=Parser)
```


## Requirements

- Python 3.4 or greater


## Installation

Library is available on PyPI and can be installed by executing

```
pip install ogn-lib
```


## Documentation

The documentation is available online at
[http://ogn-lib.readthedocs.io](http://ogn-lib.readthedocs.io/en/latest/).


## How to contribute
