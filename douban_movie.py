# coding:utf-8
import re
import time
import json
import logging
from urllib import parse

import requests

f = '[%(asctime)s][%(filename)s:%(lineno)d]' \
    '[pid=%(process)d][thread=%(thread)d]' \
    '[%(levelname)s] %(message)s'
logging.basicConfig(format=f)


class DoubanMovie:
    """use douban movie api, get movie info, search movie"""

    def __init__(self, file_name, proxy=None):
        self.logger = logging.getLogger('tipper')
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug("init begin")

        self.api_url = 'http://movie.douban.com/api/v2'
        self.session = requests.session()
        self.proxies = {} if not proxy else {'http': proxy, 'https': proxy}

        # 缓存文件相关
        self.file_name = file_name
        self.coding = 'utf-8'
        self.changed = False
        # 设置缓存有效期
        self.failure_time = 30 * 24 * 3600
        # 设置两次调用豆瓣api之间的间隔
        self.gap = 2
        self.last_use_api = 0

        # 读取缓存
        try:
            with open(self.file_name, 'r') as f:
                self.movie_db = json.load(f)
        except FileNotFoundError:
            self.movie_db = {}
            logging.warning("db file not found")

        self.logger.debug("init complete")

    def get_top_250(self):
        """
        查询豆瓣top250的电影信息
        :return: 豆瓣top250
        """
        self.logger.debug("get douban movie top 250")
        # 已缓存并且没有超期
        if self.__check_movie_id('top250'):
            return self.movie_db['top250']['list']

        top250 = []
        # 循环获取，共5次，每次50个数据
        for i in range(5):
            # 获取从top250榜单第start个开始，count个电影的数据
            url = '{0}/top250?start={1}&count={2}'
            url = url.format(self.api_url, i * 50, 50)
            html = self.__get_http_resp(url)
            result = json.loads(html)

            top250.extend([movie['id'] for movie in result['subjects']])

        self.movie_db['top250'] = {}
        self.movie_db['top250']['list'] = top250
        self.movie_db['top250']['timestamp'] = int(time.time())
        self.changed = True

        return top250

    def get_movie_info(self, keyword, key_type):
        """
        查找电影信息
        :param keyword: 条件
        :param key_type: 查询类型，如'id', 'title'等
        :return: dict格式的电影信息
        """
        self.logger.debug('查找电影 ' + keyword + key_type)
        keyword = str(keyword)
        key_type = key_type.lower()

        # 尝试在本地缓存中查找

        # type如果为id，则key要为整数且可直接查询
        if key_type == 'id':
            if not keyword.isdigit():
                return None, None
            else:
                movie_id = keyword
                if self.__check_movie_id(movie_id):
                    return movie_id, self.movie_db[movie_id]
        else:
            for movie_id in self.movie_db:
                if movie_id == 'top250':
                    continue
                d = self.movie_db[movie_id]

                # 判断type是否存在
                if key_type not in d:
                    return None, None

                if isinstance(d[key_type], list) and (keyword in d[key_type]) \
                        and self.__check_movie_id(movie_id):
                    return movie_id, d

                if isinstance(d[key_type], str) and (keyword == d[key_type]) \
                        and self.__check_movie_id(movie_id):
                    return movie_id, d

        self.logger.info("local not found, try search on douban")
        (movie_id, movieInfo) = self.__search_movie(keyword, key_type)
        if movieInfo:  # 查找成功
            if movieInfo['title'][0] == '' and key_type == 'title':
                movieInfo['title'][0] = keyword
            if movieInfo['title'][1] == '' and key_type == 'title':
                movieInfo['title'][1] = keyword

            movieInfo['timestamp'] = int(time.time())
            self.movie_db[movie_id] = movieInfo
            self.changed = True

        self.logger.debug('get movie info complete')
        return movie_id, movieInfo

    def __search_movie(self, keyword, key_type):
        """
        在线查询电影信息，当本地缓存查找不到或需要更新时才被调用
        :param keyword: 关键字
        :param key_type: 查询类型，如'id', 'title'等
        :return: (movieID, movie_db)
        """
        self.logger.debug("search movie {} {} on douban".
                          format(key_type, keyword))
        key_type = key_type.lower()
        if key_type == 'id':
            if not keyword.isdigit():
                return None, None
            else:
                movie_id = keyword
        else:
            # 查询关键字转码
            url_keyword = parse.quote(keyword, encoding=self.coding)
            url = '{0}/search?q={1}'.format(self.api_url, url_keyword)
            url = url.replace(' ', '+')
            html = self.__get_http_resp(url)
            result = json.loads(html)

            for movie in result['subjects']:
                # 判断键值是否有效
                if key_type not in movie:
                    return None, None

                # 如果是list就用in
                if isinstance(movie[key_type], list) \
                        and keyword in movie[key_type]:
                    movie_id = movie['id']
                    break
                # 如果是str就用==
                if isinstance(movie[key_type], str) \
                        and (keyword == movie[key_type]):
                    movie_id = movie['id']
                    break
            else:
                return None, None  # 未查询到

        # 通过id查询电影信息
        url = '{0}/{1}'.format(self.api_url, movie_id)
        html = self.__get_http_resp(url)
        result = json.loads(html)

        # 判断搜索结果是否有效
        if 'msg' in result:
            return None, None

        # 原名和译名
        title1 = result['title']
        title2 = result['alt_title'].split('/', 1)[0].strip()
        result['title'] = [title1, title2]
        del result['alt_title']

        # 提取id
        movie_id = re.findall('/\d+', result['id'])[0]
        movie_id = movie_id.replace('/', '')
        del result['id']

        # 修改链接
        alt = result['alt']
        result['alt'] = alt.replace('/movie/', '/subject/')

        result['timestamp'] = int(time.time())  # 添加时间戳

        return movie_id, result

    def __get_http_resp(self, url):
        """
        获取resp
        :param url: url
        :return: resp
        """
        now = time.time()
        if now - self.last_use_api < self.gap:
            time.sleep(self.gap - (now - self.last_use_api))

        r = self.session.get(url)
        self.last_use_api = time.time()

        self.logger.debug('get http resp {} ok'.format(url))
        return r.text

    def __check_movie_id(self, movie_id):
        """
        判断电影信息是否存在且有效
        :param movie_id: 豆瓣电影id
        :return: bool
        """
        movie_id = str(movie_id)

        if movie_id not in self.movie_db:
            return False

        now = int(time.time())
        if (now - self.movie_db[movie_id]['timestamp']) < self.failure_time:
            return True
        else:
            return False

    def close(self):
        """
        保存更改
        :return: 无
        """
        if not self.changed:
            return

        import os
        if os.path.exists(self.file_name):
            import shutil
            bak_file = self.file_name + '.bak'
            # 删除原备份文件
            if os.path.exists(bak_file):
                os.remove(bak_file)
            # 生成新备份文件
            shutil.move(self.file_name, bak_file)

        with open(self.file_name, 'w') as f:
            json.dump(self.movie_db, f, indent=2)
        self.changed = False


def main():
    douban = DoubanMovie('DoubanMovie.json')
    for movie_id in douban.get_top_250():
        _, movie_info = douban.get_movie_info(movie_id, 'id')
        print(movie_id, movie_info['title'])
    douban.close()


if __name__ == '__main__':
    main()
