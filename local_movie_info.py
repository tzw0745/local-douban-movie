# coding:utf-8
import os
import json
import subprocess
import configparser

import xlsxwriter

from douban_movie import DoubanMovie


def get_all_file(dir_list_bak):
    """
    递归获取父文件夹下的所有的文件
    :param dir_list_bak: 父文件夹列表
    :return: 文件集合
    """
    dir_list = list(dir_list_bak)
    file_list = []
    i = 0
    # dir_list是递增的，所以不能用for in
    while i < len(dir_list):
        for x in os.listdir(dir_list[i]):
            path = '{0}/{1}'.format(dir_list[i], x)
            if os.path.isdir(path):
                dir_list.append(path)
            elif os.path.isfile(path):
                file_list.append(path)
        i += 1
    return set(file_list)


def filter_file(file_list, ext_names):
    """
    通过扩展名过滤文件
    :param file_list: 文件列表
    :param ext_names: 要保留的文件扩展名列表
    :return: 过滤后的文件列表
    """
    result = []
    for ext in ext_names:
        result.extend(filter(lambda x: x.lower().endswith(
            ext.lower()), file_list))
    return result


def parse_director_name(director_name):
    """
    中文+英文格式的导演姓名转换成英文，否则不转换
    :param director_name: 导演姓名
    :return: 转换后的姓名
    """
    import re
    for i, ch in enumerate(director_name):
        if re.match(r'[a-zA-Z]+', ch):
            start = i
            break
    else:
        start = 0

    return director_name[start:]


def video_format(video_path):
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


def main(db):
    ini_name, _ = os.path.splitext(os.path.basename(__file__))
    cf = configparser.ConfigParser()
    cf.read('{}.ini'.format(ini_name))

    dir_list = cf.get('main', 'path').split(';')
    dir_list = [d for d in dir_list if d and os.path.exists(d)]
    file_list = get_all_file(dir_list)

    out_file = cf.get('main', 'out')

    ext_names = ['.mkv', '.rmvb', '.rm', '.wmv', '.avi', '.mpg', '.mpeg']
    movie_list = filter_file(file_list, ext_names)

    print('开始统计本地电影信息')
    local_movie = []
    for movie_path in movie_list:
        # 获取文件大小(G)
        size = round(os.path.getsize(movie_path) / (1024 * 1024 * 1024), 1)
        format_info = video_format(movie_path)

        # 获取电影名称
        movie_name = movie_path.split('/')[-1]
        movie_name = movie_name.split('.')[0]
        if '(' in movie_name:
            movie_name = movie_name.split('(')[0]
        print(movie_name)

        # 通过电影名称查找豆瓣信息
        _, db_info = db.get_movie_info(movie_name, 'title')
        if not db_info:
            print('未找到 "{0}" 的电影信息\n'.format(movie_name))
            continue
        if db_info['attrs']['director']:
            director = db_info['attrs']['director'][0]
        else:
            director = ''
        director = parse_director_name(director)

        local_movie.append({'size': size,
                            'name': movie_name,
                            'rating': float(db_info['rating']['average']),
                            'director': director,
                            'width': format_info['width'],
                            'height': format_info['height'],
                            'duration': format_info['duration'],
                            'bit_rate': format_info['bit_rate'],
                            'path': movie_path,
                            'url': db_info['alt']})
    local_movie.sort(key=lambda x: x['bit_rate'])

    print('开始统计豆瓣电影Top250')
    top250 = []
    for i, movie_id in enumerate(db.get_top_250()):
        _, db_info = douban.get_movie_info(movie_id, 'id')
        if db_info:
            if db_info['attrs']['director']:
                director = db_info['attrs']['director'][0]
            else:
                director = ''
            top250.append({'rater_num': db_info['rating']['numRaters'],
                           'rating': float(db_info['rating']['average']),
                           'director': parse_director_name(director),
                           'year': int(db_info['attrs']['year'][0]),
                           'title0': db_info['title'][0],
                           'title1': db_info['title'][1],
                           'country': ' '.join(db_info['attrs']['country']),
                           'url': db_info['alt']})
            print(db_info['title'][0])
        else:
            print('Top{0}查找失败!'.format(i))

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
    for i, info in enumerate(local_movie):
        i += 1
        worksheet.write(i, 0, info['size'], center)
        worksheet.write_url(i, 1, info['url'], link_format, info['name'])
        temp = [info['rating'], info['director'], info['width'],
                info['width'], info['duration'], info['bit_rate']]
        worksheet.write_row(i, 2, temp, center)
        worksheet.write_url(i, 8, info['path'], link_format, '播放')
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
    head = ['评分', '评分人数', '年代', '原名',
            '译名', '导演', '国家/地区', '链接']
    worksheet.write_row('A1', head, center)
    # 自动筛选
    worksheet.autofilter(0, 0, 0, len(head) - 1)
    # 写入数据
    for i, info in enumerate(top250):
        i += 1
        row = [info['rating'], info['rater_num'], info['year'], info['title0'],
               info['title1'], info['director'], info['country']]
        worksheet.write_row(i, 0, row, center)
        worksheet.write_url(i, 7, info['url'], link_format, '链接')
    # 首行冻结
    worksheet.freeze_panes(1, 0)

    # 写入完成，关闭文件
    workbook.close()


if __name__ == '__main__':
    douban = DoubanMovie('DoubanMovie.json')
    try:
        main(db=douban)
    except:
        raise
    finally:
        douban.close()
