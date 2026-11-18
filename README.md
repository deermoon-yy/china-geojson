[English](README.md) | [简体中文](README.zh-CN.md)

# china-geojson

China province / city / district GeoJSON map data (4 levels: national, province, city, district), ready for ECharts.

## Data Layout

Data is organized by administrative hierarchy — to use one province's data, just copy its folder:

```
data/
  china.json                      National map (with all province boundaries)
  location.json                   All adcodes + center/centroid coordinates
  110000_北京市/                   Beijing
    110000_full.json              Province-level map (with child boundaries)
    110101.json                   Dongcheng District boundary
    ...
  440000_广东省/                   Guangdong
    440000_full.json              Province-level map (with city boundaries)
    440100_full.json              Guangzhou city-level map (with district boundaries)
    440103.json                   Liwan District boundary
    ...
```

- One folder per province; all its cities and districts are flattened inside
- `{adcode}_full.json` — province/city-level maps containing child boundaries (served by DataV's `_full` API); `{adcode}.json` — district's own boundary
- `adcode` is the 6-digit administrative division code (lookup names/coordinates in `location.json`)

## Usage

### Register a map in ECharts

```js
// echarts 5
fetch('data/110000_北京市/110000_full.json')
  .then(res => res.json())
  .then(data => {
    echarts.registerMap('beijing', data);
  });
```

### Regenerate the data

The script uses only the Python standard library — zero third-party dependencies:

```bash
python download_geojson.py
```

Features:

- **Concurrent downloads** (5 threads by default, adjust `MAX_WORKERS` in the script)
- Prefers the DataV **v3** API, falls back to v2 automatically; `_full` requests fall back to non-child variants on 404
- Auto-retry on timeout (5 times by default), failures logged to `log/Error.txt`
- **Resume support**: a done-list (`log/done.txt`) records completed files — finished items are skipped without sending requests
- Failed files are summarized at the end; re-run the script to fill the gaps

## Data Source

[DataV.GeoAtlas](http://datav.aliyun.com/tools/atlas/) (Alibaba Cloud). Boundary data is for reference only and should not be used as official administrative boundaries.
