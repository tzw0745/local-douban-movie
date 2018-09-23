# !/usr/bin/env python
# coding:utf-8
"""
Created by tzw0745 on 2017/3/22.
"""
import json
import math
import os
import re
import time
from datetime import datetime
from urllib import parse

import lxml.html
import requests
from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.engine import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


class LoginError(Exception):
    pass


class DoubanMovie:
    """
    豆瓣电影类，获取并缓存来自豆瓣电影信息。获取方式为HTML解析，缓存方式为sqlite
    """
    base = declarative_base()

    class Table(base):
        __tablename__ = 'DoubanMovie'

        id = Column(Integer, primary_key=True)
        url = Column(String, nullable=False)
        title = Column(String, nullable=False)
        origin = Column(String, nullable=True)
        year = Column(Integer, nullable=False)
        rating = Column(Float, nullable=False)
        raters = Column(Integer, nullable=False)
        director = Column(String, nullable=False)
        tags = Column(String, nullable=False)
        regions = Column(String, nullable=False)
        iMDb = Column(String, nullable=False)
        time = Column(DateTime, nullable=False)

        def __repr__(self):
            return '<DoubanMovie(id=\'{s.id}\', title=\'{s.title}\'>'.format(s=self)

    host_index = 'https://www.douban.com/'
    host_movie = 'https://movie.douban.com/'
    host_api = 'https://api.douban.com/'
    __session = None
    __last_request = 0
    interval = 4  # HTTP请求最小间隔，单位为秒

    db_conn = None
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
        engine = create_engine('sqlite:///' + db_file)
        self.base.metadata.create_all(engine)
        self.db_conn = sessionmaker(bind=engine)()

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
            post_data['captcha-id'] = captcha_info['id']
            print(captcha_info['url'])
            print('please input captcha code: ', end='')
            post_data['captcha-solution'] = input()

        # 登陆并判断是否成功
        r = self._request(url, data=post_data)
        if r.status_code != 200:
            raise LoginError('登陆失败 {}'.format(r.status_code))
        tree = lxml.html.fromstring(r.text)
        for error in tree.cssselect('p.error'):
            raise LoginError('登陆失败 {}'.format(error.text))
        if self.__get_captcha(r.text):
            raise LoginError('验证码错误')
        title = tree.cssselect('head title')[0].text.strip()
        if '豆瓣电影' not in title:
            raise LoginError('未知错误 {}'.format(title))

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
        print('[log]request to ', url)
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
        tree = lxml.html.fromstring(self._request(url).text)
        for title in tree.cssselect('head title'):
            if '设置' in title.text:
                return True
        else:
            return False

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
            entity = self.db_conn.query(self.Table).filter(
                self.Table.title == title).first()
            if entity:
                return entity

            url = 'j/subject_suggest?q={}'.format(title)
            url = parse.urljoin(self.host_movie, url)
            head = {'X-Requested-With': 'XMLHttpRequest'}
            for suggest in self._request(url, head=head).json():
                if suggest['title'] == title:
                    _id = re.findall(r'subject/(\d+)/', suggest['url'])[0]
                    return self.get_movie_info(movie_id=_id)
            else:
                return None  # 未找到数据
        elif movie_id:
            entity = self.db_conn.query(self.Table).filter(
                self.Table.id == movie_id).first()
            if entity and (entity.time - datetime.now()).seconds <= self.expires:
                return entity

        url = parse.urljoin('subject/', str(movie_id))
        r = self._request(parse.urljoin(self.host_movie, url))
        if r.status_code != 200:
            return None

        entity = self.Table(id=movie_id, url=r.url)
        tree = lxml.html.fromstring(r.content)
        _ = tree.cssselect('span[property=v\:itemreviewed]')[0]
        try:
            entity.title, entity.origin = _.text.strip().split(maxsplit=1)
        except ValueError:  # 中文电影只有一个标题
            entity.title, entity.origin = _.text.strip(), ''
        _ = tree.cssselect('span.year')[0]
        entity.year = int(re.findall(r'\d{4}', _.text)[0])
        _ = tree.cssselect('strong[property=v\:average]')[0]
        entity.rating = float(_.text)
        _ = tree.cssselect('span[property=v\:votes]')[0]
        entity.raters = int(_.text)
        _ = tree.cssselect('a[rel=v\:directedBy]')[0]
        entity.director = _.text
        _ = tree.cssselect('span[property=v\:genre]')
        entity.tags = '/'.join(x.text.strip() for x in _)
        _ = re.findall(r'制片国家/地区:</span>(.*)<br/>', r.text)[0]
        entity.regions = '/'.join(str(x).strip() for x in _.split('/'))
        entity.imdb = re.findall(r'IMDb链接:</span> <a href="(.*?)"', r.text)[0]
        entity.time = datetime.now()
        self.db_conn.merge(entity)

        return entity

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
        self.db_conn.commit()
        self.db_conn.close()
