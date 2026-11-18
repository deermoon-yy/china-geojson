[English](README.md) | [简体中文](README.zh-CN.md)

# china-geojson

中国省市区县 GeoJSON 地图数据（含全国/省/市/区县四级，可直接用于 ECharts）。

## 数据内容

目录按行政区划层级归类，需要某个省的数据直接复制对应的省文件夹即可：

```
data/
  china.json                      全国地图（含各省边界）
  location.json                   全国区划代码 + 中心点坐标
  110000_北京市/
    110000_full.json              省级地图（含下级边界）
    110101.json                   东城区边界
    ...
  440000_广东省/
    440000_full.json              省级地图（含各市边界）
    440100_full.json              广州市地图（含各区县边界）
    440103.json                   荔湾区边界
    ...
```

- 每个省一个文件夹，市、区县文件全部平铺在省文件夹下
- `{adcode}_full.json` 为省/市级地图（含子区域边界，来自 DataV 的 `_full` 接口）；`{adcode}.json` 为区县自身边界
- `adcode` 为 6 位行政区划代码（名称、坐标可在 `location.json` 中查询）

## 使用

### ECharts 注册地图

```js
// echarts 5
fetch('data/110000_北京市/110000_full.json')
  .then(res => res.json())
  .then(data => {
    echarts.registerMap('beijing', data);
  });
```

### 重新生成数据

脚本仅依赖 Python 标准库，零第三方依赖：

```bash
python download_geojson.py
```

特性：

- **并发下载**（默认 5 线程，可通过脚本内 `MAX_WORKERS` 调整）
- 优先请求 DataV **v3** 接口，失败自动降级到 v2 地址；`_full` 接口 404 时自动降级为不含子区域的接口
- 超时自动重试（默认 5 次），失败记录到 `log/Error.txt`
- **断点续传**：完成清单（`log/done.txt`）记录已下载文件，命中的项不再发请求直接跳过
- 结束时汇总失败清单，重跑脚本即可补齐

## 数据来源

[DataV.GeoAtlas](http://datav.aliyun.com/tools/atlas/)（阿里云），边界数据仅供参考，不作为法定行政区域依据。
