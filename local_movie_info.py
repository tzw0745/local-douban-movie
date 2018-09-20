# coding:utf-8
import configparser
import copy
import json
import os
import re
import subprocess
from itertools import chain

import xlsxwriter

from douban_movie import DoubanMovie


def all_files(d):
    """
    获取目录目录下所有子文件
    :param d: 目标目录
    :return: 子文件列表
    """
    return list(os.path.join(_d, _f) for _d, _, _fl in os.walk(d) for _f in _fl)


def parse_video(video_path):
    """
    调用ffprobo获取视频解码信息
    :param video_path: 视频文件路径
    :return: 视频解码信息字典
    """
    args = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', '-i', video_path]
    info = json.loads(subprocess.check_output(args).decode('utf-8'))

    for stream in info['streams']:
        if stream['codec_type'] == 'video':
            # 获取视频宽 视频高
            video_width = int(stream['width'])
            video_height = int(stream['height'])
            break
    else:
        video_width = 0
        video_height = 0

    # 获取视频文件总码率(MB/s)
    bit_rate = int(info['format']['bit_rate']) / (1024 * 1024)

    return {'height': video_height,
            'width': video_width,
            'duration': int(float(info['format']['duration']) / 60),
            'bit_rate': round(bit_rate, 1)}


def main():
    cfg = configparser.ConfigParser()
    cfg.read('config.ini', encoding='utf-8')

    dirs = cfg.get('DEFAULT', 'path').split(';')
    match = re.compile(cfg.get('DEFAULT', 'match'))
    name_reg = re.compile(cfg.get('DEFAULT', 'name_reg'))
    out_file = cfg.get('DEFAULT', 'out')
    user = cfg.get('DEFAULT', 'username')
    pwd = cfg.get('DEFAULT', 'password')

    dirs = [_d for _d in dirs if os.path.isdir(_d)]
    files = set(chain(*[all_files(_d) for _d in dirs]))
    movies = set(filter(lambda _f: match.match(os.path.split(_f)[1]), files))

    local_movie = []
    top250 = []
    with DoubanMovie('db.sqlite3', user, pwd) as db:
        print('----开始统计本地电影信息----')
        for movie_path in movies:
            # 获取电影名称
            movie_name = name_reg.findall(os.path.split(movie_path)[1])[0]
            print(movie_name)
            # 获取电影大小(G)
            size = round(os.path.getsize(movie_path) / (1024 * 1024 * 1024), 1)
            # 调用FFmpeg获取视频信息
            video_info = parse_video(movie_path)

            # 通过电影名称获取豆瓣电影信息
            movie_info = db.get_movie_info(title=movie_name)
            if not movie_info:
                _msg = 'Movie "{0}" not found on Douban'
                raise ValueError(_msg.format(movie_name))

            local_movie.append({
                'size': size, 'name': movie_name,
                'rating': movie_info['rating'],
                'director': movie_info['director'],
                'width': video_info['width'],
                'height': video_info['height'],
                'duration': video_info['duration'],
                'bit_rate': video_info['bit_rate'],
                'path': movie_path, 'url': movie_info['url']
            })
        local_movie.sort(key=lambda x: x['bit_rate'])

        print('----开始统计豆瓣电影Top250----')
        for i, movie_id in enumerate(db.get_top250id()):
            movie_info = db.get_movie_info(movie_id=movie_id)
            top250.append({
                'rater_num': movie_info['raters'],
                'rating': float(movie_info['rating']),
                'director': movie_info['director'],
                'year': int(movie_info['year']),
                'title0': movie_info['title'],
                'title1': movie_info['origin'],
                'country': movie_info['regions'],
                'url': movie_info['url']
            })
            print('Top{:0>3}'.format(i + 1), movie_info['title'])

    print('写入{}中...'.format(out_file))
    # 创建工作簿
    workbook = xlsxwriter.Workbook(out_file)
    # 普通文本格式
    center = workbook.add_format({'align': 'center',
                                  'valign': 'vcenter'})
    # 超链接格式
    link_format = workbook.add_format({'color': 'blue',
                                       'underline': 1,
                                       'align': 'center',
                                       'valign': 'vcenter'})
    # alarm
    alarm = workbook.add_format({'color': '#9C0006',
                                 'bg_color': '#FFC7CE',
                                 'align': 'center',
                                 'valign': 'vcenter'})

    # 开始写入本地电影信息
    worksheet = workbook.add_worksheet('本地电影列表')
    # 设置列宽
    worksheet.set_column('A:G', 12)
    worksheet.set_column('B:B', 30)
    worksheet.set_column('D:D', 20)
    # 写入表头
    head = ['大小(G)', '电影名称', '豆瓣评分', '导演', '视频宽度',
            '视频高度', '时长(min)', '总码率(Mb)', '链接']
    worksheet.write_row('A1', head, center)
    # 自动筛选
    worksheet.autofilter(0, 0, 0, len(head) - 1)
    # 写入数据
    for i, movie_info in enumerate(local_movie):
        i += 1
        worksheet.write(i, 0, movie_info['size'], center)
        worksheet.write_url(i, 1, movie_info['url'], link_format, movie_info['name'])
        temp = [movie_info['rating'], movie_info['director'], movie_info['width'],
                movie_info['height'], movie_info['duration'], movie_info['bit_rate']]
        worksheet.write_row(i, 2, temp, center)
        worksheet.write_url(i, 8, movie_info['path'], link_format, '播放')
    # 首行冻结
    worksheet.freeze_panes(1, 0)
    # 条件格式
    worksheet.conditional_format(
        'E2:E{}'.format(len(local_movie) + 1),
        {'type': 'cell',
         'criteria': '<=',
         'value': 1400,
         'format': alarm})

    # 开始写入豆瓣电影Top250信息
    worksheet = workbook.add_worksheet('豆瓣Top250')
    # 设置列宽
    worksheet.set_column('A:H', 12)
    worksheet.set_column('D:E', 30)
    worksheet.set_column('F:G', 20)
    # 写入表头
    head = ['评分', '评分人数', '年代', '中文名',
            '原名', '导演', '国家/地区', '链接']
    worksheet.write_row('A1', head, center)
    # 自动筛选
    worksheet.autofilter(0, 0, 0, len(head) - 1)
    # 写入数据
    for i, movie_info in enumerate(top250):
        i += 1
        row = [movie_info['rating'], movie_info['rater_num'], movie_info['year'], movie_info['title0'],
               movie_info['title1'], movie_info['director'], movie_info['country']]
        worksheet.write_row(i, 0, row, center)
        worksheet.write_url(i, 7, movie_info['url'], link_format, '链接')
    # 首行冻结
    worksheet.freeze_panes(1, 0)

    # 写入完成，关闭文件
    workbook.close()


if __name__ == '__main__':
    split_line = '-' * 80
    try:
        print(split_line)
        main()
        print('\nall done')
    except Exception as e:
        import traceback

        print(''.join([str(e), traceback.format_exc()]))
    finally:
        print(split_line)
