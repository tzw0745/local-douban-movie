# 项目说明
![](http://ofpb4e3i2.bkt.clouddn.com/16-10-31/26400320.jpg)
* 归档本地电影，评分导演等信息使用豆瓣[电影api](https://developers.douban.com/wiki/?title=movie_v2)获取
* 列出豆瓣电影top250

# LocalFilmInfo.py
* 归档本地电影（使用DoubanMovie.py）和豆瓣电影top250并将结果输出到excel文件
* 依赖xlsxwriter
* 读取与之同名的ini配置文件

# LocalFilmInfo.ini
* 供LocalFilmInfo.py读取。
* 读取[main]中的path和excel。前者是要统计的路径，后者是输出文件的路径。

# DoubanMovie.py
* 定义了 `DoubanMovie` 类。
* 初始化时指定缓存文件名：
    ```python
    douban = DoubanMovie('xx.json')
    ```

* 获取电影信息， `keyType` 一般为 `id` 或 `tite`，返回一个(movieID, movieInfo)的元组：
    ```python
    douban.GetMovieInfo(key, keyType)
    douban.GetMovieInfo('火星救援', 'title')
    ```

* 获取豆瓣电影top250，返回一个列表，包括250个id：
    ```python
    douban.GetTop250()
    ```

* 自动清除超过30天的电影数据