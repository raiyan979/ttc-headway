# Data attribution & licence

The code in this repository is licensed under the MIT License (see `LICENSE`).
The **data** is not ours and is governed separately.

## Source

Real-time vehicle positions are retrieved from the Toronto Transit Commission
(TTC) GTFS-Realtime feed, and the static schedule from the City of Toronto Open
Data portal.

## Licence

This data is made available under the **Open Government Licence – Toronto**:
https://open.toronto.ca/open-data-license/

Contains information licensed under the Open Government Licence – Toronto. Data
provided by the City of Toronto and the Toronto Transit Commission.

## No affiliation or endorsement

This is an independent portfolio project. It is **not affiliated with, endorsed
by, or sponsored by** the Toronto Transit Commission or the City of Toronto. The
Open Government Licence – Toronto requires that use not suggest any such
endorsement, and none is implied.

## Collection conduct

The collector identifies itself with a descriptive User-Agent and polls at a
bounded rate (one request per 30 seconds during defined collection windows). The
collection window is time-boxed; the collector is intentionally disabled at the
end of it (see the README).
