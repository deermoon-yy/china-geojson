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
    110000_北京市.json             Province-level map (with child boundaries)
    110101_东城区.json             District boundary (municipalities/SAARs attach directly to province)
  440000_广东省/                   Guangdong
    440000_广东省.json             Province-level map (with city boundaries)
    440100_广州市/                  Guangzhou
      440100_广州市.json           City-level map (with district boundaries)
      440103_荔湾区.json           Liwan District boundary
```

- Files/folders are named `{adcode}_{name}`, where `adcode` is the 6-digit administrative division code
- Province/city-level JSON files contain child boundaries — register them in ECharts for drill-down maps
- `location.json` holds adcodes, names, and center/centroid coordinates for marking points on maps

## Usage

### Register a map in ECharts

```js
// echarts 5
fetch('data/110000_北京市/110000_北京市.json')
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
