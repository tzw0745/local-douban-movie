#coding:utf-8
import os
import json
import subprocess
import configparser

import xlsxwriter

from DoubanMovie import DoubanMovie


'''
说明：获取dirList中所有文件夹的所有子文件夹
参数：父文件夹列表
返回：集合，dirList中所有文件夹的所有子文件夹（包括自身）
'''
def GetSubDir(dirList):
    subDir = list(dirList)
    offset = 0
    while offset < len(subDir):
        # 获取所有项目
        allElem = os.listdir(subDir[offset])
        for eachElem in allElem:
            pathString = '{0}/{1}'.format(subDir[offset], eachElem)
            # 判断是否是文件夹
            if os.path.isdir(pathString):
                subDir.append(pathString)
        offset += 1
    return set(subDir)


'''
说明：通过后缀名过滤文件
参数：文件列表，后缀名列表
返回：过滤后的文件列表
'''
def FilterExname(fileList, arrExtnames):
    filterList = []
    for fileName in fileList:
        # 转小写先
        lowFileName = fileName.lower()
        for strExtName in arrExtnames:
            # 判断是否匹配
            if lowFileName.endswith(strExtName.lower()):
                filterList.append(fileName)
    return filterList


'''
说明：格式化导演姓名，豆瓣的导演信息有中文、中+英、英文这三种形式
说明：统一格式化成英文。只有中文的就算了
参数：字符串，导演姓名
返回：格式化后的结果
'''
def DirectorProcess(directorStr):
    engStart = -1
    for i, ch in enumerate(directorStr):
        if ch.islower() or ch.isupper():
            engStart = i
            break

    if engStart == -1:
        return directorStr
    return directorStr[engStart:]


'''
说明：调用ffprobo获取视频文件解码信息
说明：ffprobe应放置在环境变量或当前工作目录中
参数：视频文件路径
返回：哈希表，存放视频解码信息
'''
def VideoDecoding(path):
    strCmd = 'ffprobe -v quiet -print_format json\
    -show_format -show_streams -i "{0}"'

    strCmd = strCmd.format(path)
    result = subprocess.Popen(strCmd,
                              shell=True,
                              stdout=subprocess.PIPE,
                              bufsize=-1).stdout.read()
    return json.loads(result.decode('utf-8'))


'''
说明：将VideoDecoding返回的字典格式化
参数：VideoDecoding的返回值
返回：(视频宽、视频高、视频长度、比特率)
'''
def FormatDecoing(info):
    # 获取视频高宽
    for stream in info['streams']:
        # 判断是否是视频流
        if (stream['codec_type'] == 'video'):
            # 获取视频宽 视频高
            videoWidth = int(stream['width'])
            videoHeight = int(stream['height'])
            break
    else:
        videoWidth = 0
        videoHeight = 0

    # 获取视频长度(分钟)
    duration = int(float(info['format']['duration']) / 60)
    # 获取视频文件总码率(MB/s)
    allBitRate = int(info['format']['bit_rate']) / (1024 * 1024)
    allBitRate = round(allBitRate, 1)

    return videoHeight, videoWidth, duration, allBitRate


'''
说明：统计本地电影和top250的信息并保存在excel文件中
参数：douban电影管理类
返回：无
'''
def main(douban):
    # 读取配置文件
    iniName, _ = os.path.splitext(os.path.basename(__file__))
    cf = configparser.ConfigParser()
    cf.read('{}.ini'.format(iniName))

    dirList = cf.get('main', 'path').split(',')
    excelFile = cf.get('main', 'excel')

    dirList = [d for d in dirList if os.path.exists(d)]

    #获取所有子目录
    dirList = GetSubDir(dirList)

    #获取目录中的所有文件
    fileList = []
    for eachDir in dirList:
        allElem = os.listdir(eachDir)
        for eachElem in allElem:
            pathString = '{0}/{1}'.format(eachDir, eachElem)
            if os.path.isfile(pathString):
                fileList.append(pathString)

    # 视频文件后缀名
    extNames = ['.mkv', '.rmvb', '.rm', '.wmv', '.avi', '.mpg', '.mpeg']
    # 筛选出所有的视频文件
    movieList = FilterExname(fileList, extNames)

    #--------------------------------------
    # 获取所有本地电影文件的解码信息和其他信息
    #--------------------------------------
    print('开始统计本地电影信息')
    localFilmInfo = []
    for moviePath in movieList:
        # 获取文件大小(G)
        size = round(os.path.getsize(moviePath) / (1024 * 1024 * 1024), 1)
        # 获取解码信息
        decodingInfo = VideoDecoding(moviePath)
        height, width, duration, bitRate = FormatDecoing(decodingInfo)

        # 获取电影名
        movieName = moviePath.split('/')[-1]
        movieName = movieName.split('.')[0]
        if '(' in movieName:
            movieName = movieName.split('(')[0]
        print(movieName)

        # 通过文件名查找豆瓣信息
        _, info = douban.GetMovieInfo(movieName, 'title')
        if not info:
            print('未找到 "{0}" 的电影信息\n'.format(movieName))
            continue

        # 获取导演
        if info['attrs']['director']:
            director = info['attrs']['director'][0]
        else:
            director = ''
        director = DirectorProcess(director)

        # 组合
        infoDict = {'size': size,
                    'name': movieName,
                    'rating': float(info['rating']['average']),
                    'director': director,
                    'width': width,
                    'height': height,
                    'duration': duration,
                    'bitRate': bitRate,
                    'path': moviePath,
                    'url': info['alt']}
        localFilmInfo.append(infoDict)

    # 按比特率排序
    localFilmInfo.sort(key=lambda x: x['bitRate'])

    #---------------------------
    # 获取豆瓣电影Top250的豆瓣信息
    #---------------------------
    print('开始统计豆瓣电影Top250')
    top250Info = []
    for i, movieID in enumerate(douban.GetTop250()):
        _, info = douban.GetMovieInfo(movieID, 'id')
        if info:
            director = info['attrs']['director'][0]

            infoDict = {'numRaters': info['rating']['numRaters'],
                        'rating': float(info['rating']['average']),
                        'director': DirectorProcess(director),
                        'year': int(info['attrs']['year'][0]),
                        'title0': info['title'][0],
                        'title1': info['title'][1],
                        'country': ' '.join(info['attrs']['country']),
                        'url': info['alt']}
            top250Info.append(infoDict)
            print(infoDict['title0'])
        else:
            print('Top{0}查找失败!'.format(i))

    #---------------------------
    # 将本地电影信息和豆瓣电影Top250信息写入Excel
    #---------------------------
    # 创建工作簿
    workbook = xlsxwriter.Workbook(excelFile)

    # 普通文本格式
    center = workbook.add_format({'align': 'center',
                                  'valign': 'vcenter'})
    # 超链接格式
    linkFormat = workbook.add_format({'color': 'blue',
                                      'underline': 1,
                                      'align': 'center',
                                      'valign': 'vcenter'})
    # alarm
    alarm = workbook.add_format({'color': '#9C0006',
                                 'bg_color': '#FFC7CE',
                                 'align': 'center',
                                 'valign': 'vcenter'})

    #开始写入本地电影信息
    worksheet = workbook.add_worksheet('本地电影列表')
    #设置列宽
    worksheet.set_column('A:G', 12)
    worksheet.set_column('B:B', 30)
    worksheet.set_column('D:D', 20)

    head= ['大小(G)', '电影名称', '豆瓣评分', '导演', '视频宽度']
    head.extend(['视频高度', '时长(min)', '总码率(Mb)', '链接'])
    # 添加表头
    worksheet.write_row('A1', head, center)
    # 设置表头为自动筛选
    worksheet.autofilter(0, 0, 0, len(head) - 1)

    for i, infoDict in enumerate(localFilmInfo):
        i += 1
        worksheet.write(i, 0, infoDict['size'], center)
        worksheet.write_url(i, 1, infoDict['url'], linkFormat, infoDict['name'])
        worksheet.write(i, 2, infoDict['rating'], center)
        worksheet.write(i, 3, infoDict['director'], center)
        worksheet.write(i, 4, infoDict['width'], center)
        worksheet.write(i, 5, infoDict['height'], center)
        worksheet.write(i, 6, infoDict['duration'], center)
        worksheet.write(i, 7, infoDict['bitRate'], center)
        worksheet.write_url(i, 8, infoDict['path'], linkFormat, '播放')
    # Freeze the first row.
    worksheet.freeze_panes(1, 0)

    worksheet.conditional_format(
        'E2:E{}'.format(len(localFilmInfo) + 1),
        {'type': 'cell',
         'criteria': '<=',
         'value': 1400,
         'format': alarm})

    #开始写入豆瓣电影Top250信息
    worksheet = workbook.add_worksheet('豆瓣Top250')
    #设置列宽
    worksheet.set_column('A:H', 12)
    worksheet.set_column('D:E', 30)
    worksheet.set_column('F:G', 20)

    head = ['评分', '评分人数', '年代', '原名']
    head.extend(['译名', '导演', '国家/地区', '链接'])
    # 添加表头
    worksheet.write_row('A1', head, center)
    # 设置表头为自动筛选
    worksheet.autofilter(0, 0, 0, len(head) - 1)

    for i, infoDict in enumerate(top250Info):
        i += 1
        worksheet.write(i, 0, infoDict['rating'], center)
        worksheet.write(i, 1, infoDict['numRaters'], center)
        worksheet.write(i, 2, infoDict['year'], center)
        worksheet.write(i, 3, infoDict['title0'], center)
        worksheet.write(i, 4, infoDict['title1'], center)
        worksheet.write(i, 5, infoDict['director'], center)
        worksheet.write(i, 6, infoDict['country'], center)
        worksheet.write_url(i, 7, infoDict['url'], linkFormat, '链接')
    # Freeze the first row.
    worksheet.freeze_panes(1, 0)

    #写入完成，关闭文件
    workbook.close()

if __name__ == '__main__':
    # 初始化类
    douban = DoubanMovie('DoubanMovie.json')
    try:
        main(douban)
    except:
        raise
    finally:
        douban.Close()
