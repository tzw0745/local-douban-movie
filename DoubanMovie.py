#coding:utf-8
import json, time, re
from urllib import parse, request
from io import BytesIO
import gzip
import urllib


class DoubanMovie():
    '''use douban movie api, get movie info, search movie'''

    def __init__(self, fileName):
        self.apiUrl = 'https://movie.douban.com/api/v2'
        # 确保每两次调用之间的间隔超过10秒
        self.lastTime = 0
        self.sleepTime = 10

        # 缓存文件名
        self.fileName = fileName
        self.coding = 'utf-8'
        self.changed = False
        # 设置缓存有效期
        self.failureTime = 30 * 24 * 3600

        # 读取缓存
        try:
            with open(self.fileName, 'r', encoding=self.coding) as f:
                self.movieDict = json.load(f)
        except FileNotFoundError:
            self.movieDict = {}


    '''
    返回豆瓣top250的电影信息
    '''
    def GetTop250(self):
        # 已缓存并且没有超期
        if self.__CheckMovieID('top250'):
            return self.movieDict['top250']['list']

        top250 = []
        # 循环获取，共5次，每次50个数据
        for i in range(5):
            # 获取从top250榜单第start个开始，count个电影的数据
            url = '{0}/top250?start={1}&count={2}'
            url = url.format(self.apiUrl, i * 50, 50)
            html = self.__GetHttp(url)
            result = json.loads(html)

            top250.extend([movie['id'] for movie in result['subjects']])

        self.movieDict['top250'] = {}
        self.movieDict['top250']['list'] = top250
        self.movieDict['top250']['timestamp'] = int(time.time())
        self.changed = True

        return top250


    '''
    说明：以keyword为条件查找电影信息，keyType为查询类型
    参数：keyType可为'id', 'title'等。当keyType为'id'时keyword为整数
    返回：dict格式的电影信息
    '''
    def GetMovieInfo(self, keyword, keyType):
        keyword = str(keyword)
        keyType = keyType.lower()

        # 尝试在本地缓存中查找

        # type如果为id，则key要为整数且可直接查询
        if keyType == 'id':
            if not keyword.isdigit():
                return (None, None)
            else:
                movieID = keyword
                if self.__CheckMovieID(movieID):
                    return (movieID, self.movieDict[movieID])
        else:
            for movieID in self.movieDict:
                if movieID == 'top250':
                    continue
                d = self.movieDict[movieID]

                # 判断type是否存在
                if keyType not in d:
                    return (None, None)

                if isinstance(d[keyType], list) and (keyword in d[keyType])\
                    and self.__CheckMovieID(movieID):
                    return (movieID, d)

                if isinstance(d[keyType], str) and (keyword == d[keyType])\
                    and self.__CheckMovieID(movieID):
                    return (movieID, d)

        #本地不存在，在线查找
        (movieID, movieInfo) = self.__SearchMovie(keyword, keyType)
        if movieInfo:  #查找成功
            if movieInfo['title'][0] == '' and keyType == 'title':
                movieInfo['title'][0] = keyword
            if movieInfo['title'][1] == '' and keyType == 'title':
                movieInfo['title'][1] = keyword

            movieInfo['timestamp'] = int(time.time())
            self.movieDict[movieID] = movieInfo
            self.changed = True

        return (movieID, movieInfo)


    '''
    说明：在线查询电影信息，类内部访问，当本地缓存查找不到或更新时才被调用
    参数：keyword为查询关键字，keyType可以为'title', 'id'等等
    返回：元祖格式的电影信息：(movieID, movieDict)
    '''
    def __SearchMovie(self, keyword, keyType):
        keyType = keyType.lower()
        if keyType == 'id':
            if not keyword.isdigit():
                return (None, None)
            else:
                movieID = keyword
        else:
            # 查询关键字转码
            urlKeyword = parse.quote(keyword, encoding=self.coding)
            url = '{0}/search?q={1}'.format(self.apiUrl, urlKeyword)
            url = url.replace(' ', '+')
            html = self.__GetHttp(url)
            result = json.loads(html)

            for movie in result['subjects']:
                # 判断键值是否有效
                if keyType not in movie:
                    return (None, None)

                # 如果是list就用in
                if isinstance(movie[keyType], list)\
                    and keyword in movie[keyType]:
                    movieID = movie['id']
                    break
                # 如果是str就用==
                if isinstance(movie[keyType], str)\
                    and (keyword == movie[keyType]):
                    movieID = movie['id']
                    break
            else:
                return (None, None)  #未查询到

        # 通过id查询电影信息
        url = '{0}/{1}'.format(self.apiUrl, movieID)
        html = self.__GetHttp(url)
        result = json.loads(html)

        # 判断搜索结果是否有效
        if 'msg' in result:
            return (None, None)

        # 原名和译名
        title1 = result['title']
        title2 = result['alt_title'].split('/', 1)[0].strip()
        result['title'] = [title1, title2]
        del result['alt_title']

        #提取id
        movieID = re.findall('/\d+', result['id'])[0]
        movieID = movieID.replace('/', '')
        del result['id']

        #修改链接
        alt = result['alt']
        result['alt'] = alt.replace('/movie/', '/subject/')

        result['timestamp'] = int(time.time())  #添加时间戳
        return (movieID, result)


    '''
    说明：定制化的获取httpResp，每次间隔时间为self.sleepTime
    '''
    def __GetHttp(self, url):
        now = int(time.time())
        if (now - self.lastTime) < self.sleepTime:
            time.sleep(self.sleepTime + self.lastTime - now)

        req = request.Request(url)
        response = request.urlopen(req)
        html = response.read()
        if response.info().get('Content-Encoding') == 'gzip':
            buf = BytesIO(html)
            f = gzip.GzipFile(fileobj=buf)
            html = f.read()

        self.lastTime = int(time.time())
        return html.decode('utf-8')


    '''
    说明：当id电影信息已缓存并没有超期时返回True。
    参数：整数形式的id，或者是top250。
    '''
    def __CheckMovieID(self, movieID):
        movieID = str(movieID)

        if movieID not in self.movieDict:
            return False

        now = int(time.time())
        if (now - self.movieDict[movieID]['timestamp']) < self.failureTime:
            return True
        else:
            return False


    '''
    说明：持久化保存movieDict
    '''
    def Close(self):
        if not self.changed:
            return

        import os
        if os.path.exists(self.fileName):
            import shutil
            bakFile = self.fileName + '.bak'
            # 删除原备份文件
            if os.path.exists(bakFile):
                os.remove(bakFile)
            # 生成新备份文件
            shutil.move(self.fileName, bakFile)

        with open(self.fileName, 'w', encoding=self.coding) as f:
            json.dump(self.movieDict, f, indent=2)
        self.changed = False

if __name__ == '__main__':
    douban = DoubanMovie('DoubanMovie.json')
    result = douban.GetMovieInfo('彗星来的那一夜', 'title')
    print(result[1])
    douban.Close()
