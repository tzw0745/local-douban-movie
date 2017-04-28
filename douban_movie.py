# !/usr/bin/env python
# coding:utf-8
"""
Created by tzw0745 on 2017/3/22.
"""
import re
import os
import time
import json
import sqlite3
from datetime import datetime

import requests
import lxml.html


class LoginError(Exception):
    pass


class DoubanMovie:
    def __init__(self, db_file, username, pwd, cookie_dir='cookie'):
        """
        初始化类。
        :param db_file: 数据库文件名
        :param username: 用户名
        :param pwd: 密码
        :param cookie_dir: cookie保存的文件夹
        """
        # 判断参数是否有效&初始化参数
        if not re.match(r'^\w+@\w+\.\w+$', username) and \
                not re.match(r'^[0-9]{11}$', username):
            raise KeyError('用户名必须是邮箱或手机号')

        self.failed_days = 15
        self.server = 'https://movie.douban.com/'
        self.s = requests.session()

        # 开启数据库
        self.table_name = 'DoubanMovie'
        temp = '''CREATE TABLE {}
                                          (id       INT  PRIMARY KEY,
                                           url      TEXT NOT NULL,
                                           title    TEXT NOT NULL,
                                           origin   TEXT,
                                           year     INT  NOT NULL,
                                           rating   FLOAT NOT NULL,
                                           raters   INT NOT NULL,
                                           director TEXT NOT NULL,
                                           tags     TEXT NOT NULL,
                                           regions  TEXT NOT NULL,
                                           iMDb     TEXT NOT NULL,
                                           time     DATE NOT NULL)'''.format(self.table_name)
        self.conn = connect_db(db_file, self.table_name, temp)

        # 从本地载入cookie并判断是否有效
        if not os.path.exists(cookie_dir):
            os.mkdir(cookie_dir)
        cookie_path = '{}/{}.json'.format(cookie_dir, username)
        if os.path.exists(cookie_path):
            with open(cookie_path, 'r') as f:
                self.s.cookies.update(json.load(f))
            if not self.is_online():
                self.s.cookies.clear()
            else:
                return

        # 登陆准备，包括获取验证码
        url = '{}login'.format(self.server.replace('movie', 'www'))
        post_data = {'source': 'index_nav',
                     'redir': self.server,
                     'form_email': username,
                     'form_password': pwd,
                     'remember': 'on',
                     'login': '登录'}
        r = self.s.get(url)
        if r.text == 'Please try later.' and r.status_code == 403:
            raise LoginError('your IP has been blocked')
        captcha = self.__get_captcha(r.text)
        if captcha:
            captcha_file = 'captcha.jpg'
            post_data['captcha-id'] = captcha['id']
            with open(captcha_file, 'wb') as f:
                f.write(self.s.get(captcha['url']).content)
            os.system(captcha_file)
            print('please input captcha code: ', end='')
            post_data['captcha-solution'] = input()
            os.remove(captcha_file)

        # 登陆并判断是否成功
        r = self.s.post(url, data=post_data)
        if r.status_code != 200:
            raise LoginError('登陆失败 {}'.format(r.status_code))
        tree = lxml.html.fromstring(r.text)
        for error in tree.cssselect('p.error'):
            raise LoginError('登陆失败 {}'.format(error.text))
        if self.__get_captcha(r.text):
            raise LoginError('验证码错误')

        # 保存本地cookie
        with open(cookie_path, 'w') as f:
            json.dump(self.s.cookies.get_dict(), f, indent=2)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __get_captcha(self, html):
        """
        获取页面中的验证码信息
        :param html: html代码
        :return: 验证码信息
        """
        tree = lxml.html.fromstring(html)

        for img in tree.cssselect('input[name=captcha\-id]'):
            captcha_id = img.get('value')
            url = '{}misc/captcha?id={}'.format(self.server, captcha_id)
            return {'url': url.replace('movie.', 'www.'),
                    'id': captcha_id}

    def is_online(self):
        """
        判断当前是否在线
        :return: 无
        """
        url = '{}settings/'.format(self.server)
        r = self.s.get(url)
        for title in re.findall(r'<title>(.*)</title>', r.text):
            if '登录豆瓣' == title:
                return False
        else:
            return True

    def get_movie_info(self, title=None, movie_id=None, retry=3):
        """
        获取豆瓣电影信息
        :param title: 电影名称
        :param movie_id: 电影豆瓣id
        :param retry: 重试次数
        :return: 电影信息字典
        """
        if title == movie_id is None:
            raise KeyError('电影名称、电影id必须要有一个')

        if title is not None:
            temp = 'SELECT * FROM {} WHERE title=?'.format(self.table_name)
            cur = self.conn.execute(temp, (title,))
            for info in dict_gen(cur):
                return self.get_movie_info(movie_id=info['id'])

            url = '{}j/subject_suggest?q={}'.format(self.server, title)
            head = {'X-Requested-With': 'XMLHttpRequest'}
            for suggest in self.s.get(url, headers=head).json():
                if suggest['title'] == title:
                    temp = re.findall(r'subject/(\d+)/', suggest['url'])[0]
                    return self.get_movie_info(movie_id=temp)
            else:
                return {}  # 未找到数据

        elif movie_id is not None:
            if not str(movie_id).isdigit():
                raise KeyError('电影id必须为纯数字')

            temp = 'SELECT * FROM {} WHERE id=?'.format(self.table_name)
            cur = self.conn.execute(temp, (str(movie_id),))
            for info in dict_gen(cur):
                then = datetime.strptime(info['time'], '%Y-%m-%d %X.%f')
                if (datetime.now() - then).days >= self.failed_days:
                    break
                return info

        url = 'https://movie.douban.com/subject/{}/'.format(movie_id)
        for i in range(retry):
            try:
                r = self.s.get(url)
                break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            r = self.s.get(url)

        if r.status_code != 200:
            return {}  # 获取页面失败
        r.encoding = 'utf-8'

        tree = lxml.html.fromstring(r.text)
        temp = tree.cssselect('span[property=v\:itemreviewed]')[0]
        try:
            title, origin = temp.text.strip().split(maxsplit=1)
        except ValueError:  # 中文电影只有一个标题
            title, origin = temp.text.strip(), ''
        temp = tree.cssselect('span.year')[0]
        year = int(re.findall(r'\d{4}', temp.text)[0])
        temp = tree.cssselect('strong[property=v\:average]')[0]
        rating = float(temp.text)
        temp = tree.cssselect('span[property=v\:votes]')[0]
        raters = int(temp.text)
        temp = tree.cssselect('a[rel=v\:directedBy]')[0]
        director = temp.text
        temp = tree.cssselect('span[property=v\:genre]')
        tags = '/'.join(x.text.strip() for x in temp)
        temp = re.findall(r'制片国家/地区:</span>(.*)<br/>', r.text)[0]
        regions = '/'.join(str(x).strip() for x in temp.split('/'))
        imdb = re.findall(r'IMDb链接:</span> <a href="(.*?)"', r.text)[0]

        temp = 'REPLACE INTO {} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)'
        url = '{}subject/{}/'.format(self.server, movie_id)
        data = (movie_id, url, title, origin, year, rating, raters,
                director, tags, regions, imdb, datetime.now())
        self.conn.execute(temp.format(self.table_name), data)
        self.conn.commit()

        return self.get_movie_info(movie_id=movie_id)

    def get_top250(self):
        """
        获取豆瓣电影top250列表
        :return: 电影id列表
        """
        top250 = []
        for i in range(5):
            url = '{0}v2/movie/top250?start={1}&count={2}'
            url = url.format(self.server.replace('movie', 'api'), i * 50, 50)
            result = self.s.get(url)
            top250.extend([x['id'] for x in result.json()['subjects']])

            time.sleep(0.5)

        return top250

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
