# coding:utf-8
import os
import copy
import json
import subprocess
import configparser

import re
import xlsxwriter

from douban_movie import DoubanMovie


def get_all_file(dir_list):
    """
    递归获取父文件夹下的所有的文件
    :param dir_list: 父文件夹列表
    :return: 文件集合
    """
    work_dir_list = copy.copy(dir_list)
    file_list = []
    i = 0
    # dir_list是递增的，所以不能用for in
    while i < len(work_dir_list):
        for x in os.listdir(work_dir_list[i]):
            path = '{0}/{1}'.format(work_dir_list[i], x)
            if os.path.isdir(path):
                work_dir_list.append(path)
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
        result.extend(
            filter(lambda x: x.lower().endswith(ext.lower()), file_list)
        )
    return result


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


def main():
    ini_name, _ = os.path.splitext(os.path.basename(__file__))
    cfg = configparser.ConfigParser()
    cfg.read('{}.ini'.format(ini_name))

    dir_list = cfg.get('main', 'path').split(';')
    dir_list = [d for d in dir_list if d and os.path.exists(d)]
    file_list = get_all_file(dir_list)

    out_file = cfg.get('main', 'out')
    user = cfg.get('main', 'username')
    pwd = cfg.get('main', 'password')

    ext_names = ['.mkv', '.rmvb', '.rm', '.wmv', '.avi', '.mpg', '.mpeg']
    movie_list = filter_file(file_list, ext_names)

    local_movie = []
    top250 = []
    with DoubanMovie('douban_movie.db', user, pwd) as db:
        print('----开始统计本地电影信息----')
        for movie_path in movie_list:
            # 获取文件大小(G)
            size = round(os.path.getsize(movie_path) / 1073741824, 1)
            format_info = video_format(movie_path)

            # 获取电影名称
            movie_name = movie_path.split('/')[-1]
            movie_name = movie_name[:movie_name.rfind('.')]
            if re.match(r'^[a-zA-Z0-9]+$', movie_name):
                continue
            movie_name = movie_name.split('.')[-1]
            movie_name = re.split(r'[\[\(]+', movie_name)[0]
            print(movie_name)

            # 通过电影名称查找豆瓣信息
            movie_info = db.get_movie_info(title=movie_name)
            if not movie_info:
                raise KeyError('未找到 "{0}" 的电影信息\n'.format(movie_name))

            local_movie.append({'size': size,
                                'name': movie_name,
                                'rating': movie_info['rating'],
                                'director': movie_info['director'],
                                'width': format_info['width'],
                                'height': format_info['height'],
                                'duration': format_info['duration'],
                                'bit_rate': format_info['bit_rate'],
                                'path': movie_path,
                                'url': movie_info['url']})
        local_movie.sort(key=lambda x: x['bit_rate'])

        print('----开始统计豆瓣电影Top250----')
        for i, movie_id in enumerate(db.get_top250()):
            info = db.get_movie_info(movie_id=movie_id)
            if info:
                top250.append({'rater_num': info['raters'],
                               'rating': float(info['rating']),
                               'director': info['director'],
                               'year': int(info['year']),
                               'title0': info['title'],
                               'title1': info['origin'],
                               'country': info['regions'],
                               'url': info['url']})
                print('Top{:0>3}'.format(i), info['title'])
            else:
                raise KeyError('Top{}({})查找失败!'.format(i, movie_id))

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
                info['height'], info['duration'], info['bit_rate']]
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
    head = ['评分', '评分人数', '年代', '中文名',
            '原名', '导演', '国家/地区', '链接']
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
