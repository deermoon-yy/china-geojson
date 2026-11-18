# -*- coding: UTF-8 -*-
# 获取 DataV V3 版本中国省市区县 geoJSON 地图数据
# 目录按行政区划层级归类：省文件夹 / 市文件夹 / 区县文件
# 支持：并发下载、超时重试、v3 失败自动降级到 v2、断点续传（已存在文件跳过）、错误日志

import json
import urllib.request
import urllib.error
import ssl
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

BASE_URL_V3 = "https://geo.datav.aliyun.com/areas_v3/bound/"
BASE_URL_V2 = "https://geo.datav.aliyun.com/areas_v2/bound/"

MAX_WORKERS = 10      # 并发线程数
RETRY_TIMES = 5       # 每个请求最多重试次数
TIMEOUT = 15          # 请求超时时间（秒）
RETRY_INTERVAL = 2    # 重试间隔（秒）
DATA_DIR = "data"     # 数据输出目录
LOG_DIR = "log"       # 日志输出目录

CONTEXT = ssl._create_unverified_context()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://datav.aliyun.com/",
}

# infos.json：adcode -> {name, children: [{adcode, name, ...}]}
INFOS = {}
NAME_OF = {}

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg)


def get_area_code_type(code):
    """根据行政区划代码判断层级：1=省 2=市 3=区县"""
    if code[2:6] == "0000":
        return "1"
    elif code[4:6] == "00":
        return "2"
    else:
        return "3"


def log_error(e, url):
    with _print_lock:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "Error.txt"), "a+", encoding="utf-8") as f:
            f.write(
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                + "\n" + str(e) + "\nin request: " + url + "\n\n"
            )


def fetch(url):
    """请求 URL 并返回 JSON 数据，失败自动重试，多次失败后切换 v2 地址"""
    urls = [url]
    if url.startswith(BASE_URL_V3):
        urls.append(BASE_URL_V2 + url[len(BASE_URL_V3):])
    for i, u in enumerate(urls):
        for attempt in range(RETRY_TIMES):
            try:
                req = urllib.request.Request(u, headers=HEADERS)
                with urllib.request.urlopen(req, context=CONTEXT, timeout=TIMEOUT) as res:
                    return json.loads(res.read().decode("UTF-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
                log("请求失败（第%d次）：%s -> %s" % (attempt + 1, u, e))
                log_error(e, u)
                if attempt < RETRY_TIMES - 1:
                    # 403/429 大概率是限流，多等一会再重试
                    time.sleep(RETRY_INTERVAL * 3 if isinstance(e, urllib.error.HTTPError) and e.code in (403, 429) else RETRY_INTERVAL)
        if i < len(urls) - 1:
            log("v3 地址多次失败，切换为 v2 地址重试")
    raise RuntimeError("最终请求失败：" + url)


def write_json(path, data):
    """写入 JSON 文件，文件已存在则跳过（断点续传）"""
    if os.path.exists(path):
        log("文件已存在，跳过：" + path)
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log("写入：" + path)


def load_infos():
    global INFOS, NAME_OF
    INFOS = fetch(BASE_URL_V3 + "infos.json")
    for code, val in INFOS.items():
        if "name" in val:
            NAME_OF[code] = val["name"]
        for child in val.get("children", []):
            cad = str(child["adcode"])
            NAME_OF[cad] = child["name"]


def dir_name(code):
    return "%s_%s" % (code, NAME_OF.get(code, code))


def file_name(code):
    return "%s_%s.json" % (code, NAME_OF.get(code, code))


def province_dir(code):
    return dir_name(code)


def download_one(url, path):
    """下载单个文件并写入，返回 (url, path, 错误或None)"""
    try:
        data = fetch(url)
        write_json(path, data)
        return (url, path, None)
    except RuntimeError as e:
        return (url, path, e)


def download_all(tasks):
    """并发执行下载任务，汇总失败项"""
    failures = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(download_one, url, path) for url, path in tasks]
        for fut in as_completed(futures):
            url, path, err = fut.result()
            if err is not None:
                log("失败：%s -> %s" % (path, err))
                failures.append(path)
    return failures


def build_tasks():
    """收集所有下载任务：(url, 输出路径)"""
    tasks = []

    for pcode in sorted(INFOS):
        if get_area_code_type(pcode) != "1" or pcode == "100000":
            continue
        pdir = os.path.join(DATA_DIR, province_dir(pcode))
        # 省级地图（含下级边界）
        tasks.append((BASE_URL_V3 + pcode + "_full.json", os.path.join(pdir, file_name(pcode))))

        for child in INFOS[pcode].get("children", []):
            ccode = str(child["adcode"])
            if ccode in INFOS and INFOS[ccode].get("children"):
                # 市级：市级地图 + 区县文件
                cdir = os.path.join(pdir, dir_name(ccode))
                tasks.append((BASE_URL_V3 + ccode + "_full.json", os.path.join(cdir, file_name(ccode))))
                for gc in INFOS[ccode].get("children", []):
                    gcode = str(gc["adcode"])
                    tasks.append((BASE_URL_V3 + gcode + ".json", os.path.join(cdir, file_name(gcode))))
            else:
                # 直辖市/港澳等：区划直接挂在省下
                tasks.append((BASE_URL_V3 + ccode + ".json", os.path.join(pdir, file_name(ccode))))

    return tasks


def main():
    print("请求行政区划信息接口...")
    load_infos()
    write_json(os.path.join(DATA_DIR, "location.json"), INFOS)

    # 全国地图
    data = fetch(BASE_URL_V3 + "100000_full.json")
    write_json(os.path.join(DATA_DIR, "china.json"), data)

    tasks = build_tasks()
    print("\n共 %d 个文件，%d 线程并发下载..." % (len(tasks), MAX_WORKERS))
    failures = download_all(tasks)

    if failures:
        print("\n以下 %d 个文件下载失败，可重跑脚本续传：" % len(failures))
        for p in failures:
            print("  " + p)
    else:
        print("\n全部完成")


if __name__ == "__main__":
    main()
