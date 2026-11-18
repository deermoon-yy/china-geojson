# china-geojson

中国省市区县 GeoJSON 地图数据（含全国/省/市/区县四级，可直接用于 ECharts）。

## 数据内容

目录按行政区划层级归类，需要某个省的数据直接复制对应的省文件夹即可：

```
data/
  china.json                      全国地图（含各省边界）
  location.json                   全国区划代码 + 中心点坐标
  110000_北京市/
    110000_北京市.json            省级地图（含下级边界）
    110101_东城区.json            区县边界（直辖市/港澳的区划直接挂在省下）
  440000_广东省/
    440000_广东省.json            省级地图（含各市边界）
    440100_广州市/
      440100_广州市.json          市级地图（含各区县边界）
      440103_荔湾区.json          区县自身边界
```

- 文件/文件夹名为 `{adcode}_{名称}`，`adcode` 为 6 位行政区划代码
- 省级、市级 `xxx.json` 为含子区域的完整地图，可注册到 ECharts 直接按层级下钻
- 行政区划代码、名称、center/centroid 坐标集中在 `location.json`，用于定位/标点

## 使用

### ECharts 注册地图

```js
// echarts 5
fetch('data/110000_北京市/110000_北京市.json')
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

- **并发下载**（默认 20 线程，可通过脚本内 `MAX_WORKERS` 调整）
- 优先请求 DataV **v3** 接口，多次失败自动降级到 v2 地址
- 超时自动重试（默认 5 次），失败记录到 `log/Error.txt`
- **断点续传**：已存在的文件自动跳过，中断后重跑即可继续
- 结束时汇总失败清单，重跑脚本即可补齐

## 数据来源

[DataV.GeoAtlas](http://datav.aliyun.com/tools/atlas/)（阿里云），边界数据仅供参考，不作为法定行政区域依据。
