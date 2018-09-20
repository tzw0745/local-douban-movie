# !/usr/bin/env python
# coding:utf-8
"""
Created by tzw0745 on 2017/3/22.
"""
import json
import math
import os
import re
import sqlite3
import time
import datetime
from urllib import parse

import lxml.html
import requests


class LoginError(Exception):
    pass


class DoubanMovie:
    """
    豆瓣电影类，获取并缓存来自豆瓣电影信息。获取方式为HTML解析，缓存方式为sqlite
    """
    host_index = 'https://www.douban.com/'
    host_movie = 'https://movie.douban.com/'
    host_api = 'https://api.douban.com/'
    __session = None
    __last_request = 0
    interval = 2  # HTTP请求最小间隔，单位为秒

    db_conn = None
    db_table = 'DoubanMovie'
    expires = 15 * 24 * 3600  # 缓存失效期，单位为秒

    def __init__(self, db_file: str, username: str, pwd: str, cookies_dir='cookies'):
        """
        初始化类
        :param db_file: 数据库文件名
        :param username: 豆瓣用户名
        :param pwd: 豆瓣密码
        :param cookies_dir: cookies文件夹
        """
        if not all(_ and isinstance(_, str)
                   for _ in [db_file, username, pwd, cookies_dir]):
            raise TypeError('All params must be str')

        self.__session = requests.session()
        # 初始化数据库连接
        _sql = ("CREATE TABLE {}"
                "(id       INT  PRIMARY KEY,\n"
                "url      TEXT NOT NULL,\n"
                "title    TEXT NOT NULL,\n"
                "origin   TEXT,\n"
                "year     INT  NOT NULL,\n"
                "rating   FLOAT NOT NULL,\n"
                "raters   INT NOT NULL,\n"
                "director TEXT NOT NULL,\n"
                "tags     TEXT NOT NULL,\n"
                "regions  TEXT NOT NULL,\n"
                "iMDb     TEXT NOT NULL,\n"
                "time     DATE NOT NULL)").format(self.db_table)
        self.conn = connect_db(db_file, self.db_table, _sql)

        # 载入本地cookies
        os.mkdir(cookies_dir) if not os.path.exists(cookies_dir) else None
        _cookies = os.path.join(cookies_dir, 'cookies_' + username + '.json')
        if os.path.exists(_cookies):
            with open(_cookies, 'r', encoding='utf-8') as f:
                self.__session.cookies.update(json.load(f))
            if self.is_online():
                return  # Cookies有效
            self.__session.cookies.clear()

        # 登陆准备，包括获取验证码
        url = parse.urljoin(self.host_index, 'login')
        post_data = {'source': 'index_nav',
                     'redir': self.host_movie,
                     'form_email': username,
                     'form_password': pwd,
                     'remember': 'on',
                     'login': '登录'}
        r = self._request(url)
        if 'Please try later.' in r.text and r.status_code == 403:
            raise LoginError('IP has been blocked')
        captcha_info = self.__get_captcha(r.text)
        if captcha_info:
            captcha_file = 'captcha.jpg'
            post_data['captcha-id'] = captcha_info['id']
            with open(captcha_file, 'wb') as f:
                f.write(self._request(captcha_info['url']).content)
            os.system(captcha_file)
            print('please input captcha code: ', end='')
            post_data['captcha-solution'] = input()
            os.remove(captcha_file)

        # 登陆并判断是否成功
        r = self._request(url, data=post_data)
        if r.status_code != 200:
            raise LoginError('登陆失败 {}'.format(r.status_code))
        tree = lxml.html.fromstring(r.text)
        for error in tree.cssselect('p.error'):
            raise LoginError('登陆失败 {}'.format(error.text))
        if self.__get_captcha(r.text):
            raise LoginError('验证码错误')

        # 保存本地cookie
        with open(_cookies, 'w') as f:
            json.dump(self.__session.cookies.get_dict(), f, indent=2)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _request(self, url: str, retry=3, head=None, data=None):
        """
        隐藏session，控制HTTP请求频率
        :param url: 请求链接
        :param retry: 重试次数
        :param head: HTTP请求头
        :param data: post数据，存在时发送POST请求
        :return: request.Response对象
        """
        # print('[log]request to ', url)
        if time.time() - self.__last_request < self.interval:
            time.sleep(math.ceil(time.time() - self.__last_request))
        func = self.__session.post if data else self.__session.get
        for _ in range(retry):
            try:
                r = func(url, headers=head, data=data)
                break
            except requests.RequestException:
                continue
        else:
            r = func(url, headers=head, data=data)
        self.__last_request = time.time()

        return r

    def __get_captcha(self, html):
        """
        获取页面中的验证码信息
        :param html: html代码
        :return: 验证码信息
        """
        tree = lxml.html.fromstring(html)

        for img in tree.cssselect('input[name=captcha\-id]'):
            captcha_id = img.get('value')
            url = 'misc/captcha?id={}'.format(captcha_id)
            return {'url': parse.urljoin(self.host_index, url),
                    'id': captcha_id}

    def is_online(self):
        """
        判断当前是否在线
        :return: 无
        """
        url = parse.urljoin(self.host_index, 'settings')
        r = self._request(url)
        for title in re.findall(r'<title>(.*)</title>', r.text):
            if '登录豆瓣' == title:
                return False
        else:
            return True

    def get_movie_info(self, movie_id=None, title=None):
        """
        通过电影名称或电影id获取豆瓣电影信息。两个条件中最少要有一个，movie_id优先级更高
        :param movie_id: 电影id
        :param title: 电影名称
        :return: 电影信息字典
        """
        if not any([title, movie_id]):
            raise TypeError('Param "title" and "movie_id" cant all empty')
        if movie_id and not str(movie_id).isdigit():
            raise TypeError('Param "movie" must be digit str')

        if title:
            _sql = "SELECT * FROM {} WHERE title=?".format(self.db_table)
            cursor = self.conn.execute(_sql, (title,))
            for info in dict_gen(cursor):
                return self.get_movie_info(movie_id=info['id'])

            url = 'j/subject_suggest?q={}'.format(title)
            url = parse.urljoin(self.host_movie, url)
            head = {'X-Requested-With': 'XMLHttpRequest'}
            for suggest in self._request(url, head=head).json():
                if suggest['title'] == title:
                    _id = re.findall(r'subject/(\d+)/', suggest['url'])[0]
                    return self.get_movie_info(movie_id=_id)
            else:
                return {}  # 未找到数据
        elif movie_id:
            _sql = 'SELECT * FROM {} WHERE id=?'.format(self.db_table)
            cursor = self.conn.execute(_sql, (str(movie_id),))
            for info in dict_gen(cursor):
                stamp = datetime.datetime.strptime(info['time'], '%Y-%m-%d %X.%f')
                if (datetime.datetime.now() - stamp).seconds >= self.expires:
                    break
                return info

        url = parse.urljoin('subject/', str(movie_id))
        r = self._request(parse.urljoin(self.host_movie, url))
        if r.status_code != 200:
            return {}

        tree = lxml.html.fromstring(r.content)
        _ = tree.cssselect('span[property=v\:itemreviewed]')[0]
        try:
            title, origin = _.text.strip().split(maxsplit=1)
        except ValueError:  # 中文电影只有一个标题
            title, origin = _.text.strip(), ''
        _ = tree.cssselect('span.year')[0]
        year = int(re.findall(r'\d{4}', _.text)[0])
        _ = tree.cssselect('strong[property=v\:average]')[0]
        rating = float(_.text)
        _ = tree.cssselect('span[property=v\:votes]')[0]
        raters = int(_.text)
        _ = tree.cssselect('a[rel=v\:directedBy]')[0]
        director = _.text
        _ = tree.cssselect('span[property=v\:genre]')
        tags = '/'.join(x.text.strip() for x in _)
        _ = re.findall(r'制片国家/地区:</span>(.*)<br/>', r.text)[0]
        regions = '/'.join(str(x).strip() for x in _.split('/'))
        imdb = re.findall(r'IMDb链接:</span> <a href="(.*?)"', r.text)[0]

        _sql = 'REPLACE INTO {} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)'
        data = (movie_id, r.url, title, origin, year, rating, raters,
                director, tags, regions, imdb, datetime.datetime.now())
        self.conn.execute(_sql.format(self.db_table), data)
        self.conn.commit()

        return self.get_movie_info(movie_id=movie_id)

    def get_top250id(self):
        """
        获取豆瓣top250电影id列表
        :return: 电影id列表
        """
        for i in range(5):
            url = 'v2/movie/top250?start={}&count=50'.format(i * 50)
            r = self._request(parse.urljoin(self.host_api, url))
            for movie_id in [x['id'] for x in r.json()['subjects']]:
                yield movie_id

    def close(self):
        self.conn.close()


def connect_db(db_file, table_name, create_sql):
    """
    连接数据库
    :param db_file: 数据库名称
    :param table_name: 数据库表名
    :param create_sql: 创建数据库语句
    :return: 数据库连接
    """
    connect = sqlite3.connect(db_file)
    query = '''SELECT count(*) FROM sqlite_master
               WHERE type=? AND name=?'''
    table_count = [x for x in connect.execute(
        query, ('table', table_name))][0][0]
    if table_count == 0:
        connect.execute(create_sql)
        connect.commit()
    return connect


def dict_gen(cur):
    filed_names = [d[0] for d in cur.description]
    while True:
        row = cur.fetchone()
        if not row:
            return
        yield dict(zip(filed_names, row))
