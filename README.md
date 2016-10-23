# 项目说明
* 使用豆瓣的[电影api](https://developers.douban.com/wiki/?title=movie_v2)获取电影信息并缓存在本地，缓存有效期为30天。

# DoubanMovie.py
* 定义了 `DoubanMovie` 类。
* 初始化时指定缓存文件名：
    ```python
    douban = DoubanMovie('xx.json')
    ```

* 获取电影信息， `keyType` 一般为 `id` 或 `tite`，返回一个(movieID, movieInfo)的元组：
    ```python
    douban.GetMovieInfo(key, keyType)
    ```

* 获取豆瓣电影top250，返回一个列表，包括250个id：
    ```python
    douban.GetTop250()
    ```

# LocalFilmInfo.py
* 使用DoubanMovie.py来统计硬盘中电影并将结果输出到excel文件
* 依赖xlsxwriter包。
* 读取与之同名的ini配置文件

# LocalFilmInfo.ini
* 供LocalFilmInfo.py读取。
* 读取[main]中的path和excel。前者是要统计的路径，后者是输出文件的路径。