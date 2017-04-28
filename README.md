# 概要
![](http://ofpb4e3i2.bkt.clouddn.com/16-10-31/26400320.jpg)
* 归档本地电影，评分、导演等信息使用爬虫获取并使用sqlite3缓存在本地数据库中
* 登陆豆瓣成功后将cookie保存在本地
* 列出豆瓣电影top250
* 以上信息输出到Excel文件

# local_movie_info.py
* 归档本地电影并统计豆瓣电影top250（import douban_movie.py），将信息输出到excel文
* 读取与之同名的ini配置文件

# local_movie_info.ini
* 供local_movie_info.py读取。
* `main.path`指定要统计的目录列表，用分号隔开
* `main.out`指定输出excel文件的路径
* `main.username`和`main.password`用于登陆豆瓣，因为有些电影信息登陆前不可见（如“搏击俱乐部”）

# douban_movie.py
* 定义了 `DoubanMovie` 类。
* 初始化时指定缓存文件名、用户名和密码、cookie保存目录：
    ```python
    douban = DoubanMovie('xx.json', username, password)
    ```
* 获取电影信息：
    ```python
    douban.get_movie_info(id='123456')
    douban.get_movie_info(title='火星救援')
    ```
* 获取豆瓣电影top250，返回一个列表，包括250个id：
    ```python
    for movie_id in douban.get_top250():
        print(movie_id)
    ```
* 关闭数据库可使用close方法或with上下文：
    ```python
    douban.close()

    # 另一种方法：
    with Douban(...) as douban:
        ...
    ```
* 自动清除超过15天的电影数据(可调)

# 依赖
* ffprobe.exe，需将其放入环境变量或工作目录下
* lxml+requests+xlsxwriter